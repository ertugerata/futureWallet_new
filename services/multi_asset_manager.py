"""
Multi-Asset Portfolio Manager
Kripto + Borsa + Emtia + Forex varlıklarını yönetir
"""

import yfinance as yf
import ccxt
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List

class AssetManager:
    """Çoklu varlık türünü tek bir arayüzden yönetir"""
    
    ASSET_TYPES = {
        'crypto': {'prefix': '', 'source': 'ccxt'},
        'stock_tr': {'prefix': '.IS', 'source': 'yfinance'},  # BIST
        'stock_us': {'prefix': '', 'source': 'yfinance'},     # NYSE/NASDAQ
        'commodity': {'prefix': '', 'source': 'yfinance'},    # Altın, Petrol
        'forex': {'prefix': '=X', 'source': 'yfinance'}       # Döviz çiftleri
    }
    
    def __init__(self):
        self.exchange = ccxt.binance()
    
    def get_price(self, symbol: str, asset_type: str) -> float:
        """
        Varlık türüne göre güncel fiyat çeker
        
        Args:
            symbol: Varlık sembolü (BTC, THYAO, GOLD vb.)
            asset_type: 'crypto', 'stock_tr', 'commodity' vb.
        
        Returns:
            Güncel fiyat (float)
        """
        try:
            config = self.ASSET_TYPES[asset_type]
            
            if config['source'] == 'ccxt':
                # Kripto için Binance
                # Binance REST API bazen TR'den bloklanabilir veya hata verebilir
                try:
                    ticker = self.exchange.fetch_ticker(f"{symbol}/USDT")
                    return ticker['last']
                except Exception as e:
                    # Fallback to yfinance if ccxt fails (e.g. BTC-USD)
                    # print(f"CCXT Error ({symbol}): {e}, trying yfinance...")
                    return self._get_yfinance_price(f"{symbol}-USD")
            
            elif config['source'] == 'yfinance':
                # Borsa/Emtia/Forex için Yahoo Finance
                full_symbol = f"{symbol}{config['prefix']}"
                return self._get_yfinance_price(full_symbol)
                
            return None
            
        except Exception as e:
            print(f"Fiyat çekme hatası ({symbol}): {e}")
            return None
    
    def _get_yfinance_price(self, symbol: str) -> float:
        try:
            # period='1d' fetches the most recent data
            data = yf.download(symbol, period="1d", progress=False)
            if not data.empty:
                # 'Close' might be multi-index or simple series depending on yfinance version
                # Ensure we get a scalar
                val = data['Close'].iloc[-1]
                if isinstance(val, pd.Series):
                    val = val.iloc[0]
                return float(val)
        except Exception as e:
            print(f"YFinance Error ({symbol}): {e}")
        return None
    
    def get_historical_data(self, symbol: str, asset_type: str, 
                           days: int = 365) -> pd.DataFrame:
        """
        Geçmiş fiyat verisini çeker
        """
        try:
            config = self.ASSET_TYPES[asset_type]
            start_date = datetime.now() - timedelta(days=days)
            
            # Prefer yfinance for historical data generally as it's easier for plotting (except maybe very specific crypto)
            if config['source'] == 'yfinance':
                full_symbol = f"{symbol}{config['prefix']}"
                data = yf.download(full_symbol, start=start_date, progress=False)
                return data
            
            elif config['source'] == 'ccxt':
                # Try CCXT first
                try:
                    ohlcv = self.exchange.fetch_ohlcv(
                        f"{symbol}/USDT",
                        timeframe='1d',
                        limit=days
                    )
                    df = pd.DataFrame(
                        ohlcv,
                        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                    )
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    # Rename close to Close to match yfinance
                    df.rename(columns={'close': 'Close'}, inplace=True)
                    return df
                except Exception:
                    # Fallback to yfinance for crypto history if binance fails
                    full_symbol = f"{symbol}-USD"
                    data = yf.download(full_symbol, start=start_date, progress=False)
                    return data
                
        except Exception as e:
            print(f"Veri çekme hatası: {e}")
            return pd.DataFrame()
    
    def calculate_portfolio_value(self, holdings: Dict) -> Dict:
        """
        Karışık portföy değerini hesaplar
        
        Args:
            holdings: {
                'BTC': {'type': 'crypto', 'amount': 0.5},
                'THYAO': {'type': 'stock_tr', 'amount': 100},
                'GLD': {'type': 'commodity', 'amount': 50}
            }
        
        Returns:
            Toplam değer ve detaylar
        """
        total_value = 0
        details = {}
        
        for symbol, info in holdings.items():
            price = self.get_price(symbol, info['type'])
            
            if price:
                value = price * info['amount']
                total_value += value
                
                details[symbol] = {
                    'price': price,
                    'amount': info['amount'],
                    'value': value,
                    'type': info['type']
                }
            else:
                # If price fails, keep 0 but log it
                details[symbol] = {
                    'price': 0,
                    'amount': info['amount'],
                    'value': 0,
                    'type': info['type'],
                    'error': 'Price fetch failed'
                }
        
        return {
            'total': total_value,
            'assets': details,
            'timestamp': datetime.now()
        }
    
    def compare_performance(self, symbols: List[Dict], 
                           days: int = 365) -> pd.DataFrame:
        """
        Farklı varlık türlerinin performansını karşılaştırır
        
        Args:
            symbols: [
                {'symbol': 'BTC', 'type': 'crypto'},
                {'symbol': 'XU100', 'type': 'stock_tr'},
                {'symbol': 'GC=F', 'type': 'commodity'}
            ]
        
        Returns:
            Normalize edilmiş performans DataFrame'i
        """
        performance = pd.DataFrame()
        
        for item in symbols:
            data = self.get_historical_data(
                item['symbol'], 
                item['type'], 
                days
            )
            
            if not data.empty:
                # Kapanış fiyatlarını normalize et (%0'dan başlasın)
                close_col = 'Close'
                if close_col not in data.columns:
                     # sometimes case differs or multi-index
                     if 'close' in data.columns: close_col = 'close'

                if close_col in data.columns:
                    series = data[close_col]
                    if isinstance(series, pd.DataFrame):
                        series = series.iloc[:, 0]

                    first_val = series.iloc[0]
                    normalized = ((series / first_val) - 1) * 100
                    performance[item['symbol']] = normalized
        
        return performance
