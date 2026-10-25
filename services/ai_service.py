"""
AI-Powered Decision Support Service
Yatırım kararları için akıllı öneri sistemi
"""

import google.generativeai as genai
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

def get_gemini_models(api_key: str) -> List[str]:
    """
    Lists available Gemini models that support content generation.
    """
    try:
        genai.configure(api_key=api_key)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        return models
    except Exception as e:
        print(f"Error fetching models: {e}")
        return []

class DecisionSupportAI:
    """
    Karar destek AI motoru
    UYARI: Bu sistem sadece bilgilendirme amaçlıdır. 
           Yatırım tavsiyesi değildir!
    """
    
    RISK_PROFILES = {
        'conservative': {
            'name': 'Muhafazakar',
            'max_volatility': 0.15,
            'max_drawdown': 0.10,
            'crypto_limit': 0.10,
            'stock_limit': 0.40,
            'safe_assets_min': 0.50  # Altın, tahvil, nakit
        },
        'moderate': {
            'name': 'Dengeli',
            'max_volatility': 0.25,
            'max_drawdown': 0.20,
            'crypto_limit': 0.30,
            'stock_limit': 0.50,
            'safe_assets_min': 0.20
        },
        'aggressive': {
            'name': 'Agresif',
            'max_volatility': 0.50,
            'max_drawdown': 0.40,
            'crypto_limit': 0.60,
            'stock_limit': 0.70,
            'safe_assets_min': 0.05
        }
    }
    
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
    
    def analyze_portfolio_risk(self, portfolio: Dict) -> Dict:
        """
        Portföy risk analizı yapar
        
        Args:
            portfolio: {
                'BTC': {'type': 'crypto', 'value': 30000, 'returns': [...]},
                'THYAO': {'type': 'stock_tr', 'value': 20000, 'returns': [...]},
                ...
            }
        
        Returns:
            Risk raporu ve öneriler
        """
        total_value = sum(asset['value'] for asset in portfolio.values())
        
        # Varlık dağılımı
        allocation = {}
        for symbol, data in portfolio.items():
            allocation[data['type']] = allocation.get(data['type'], 0) + data['value']
        
        allocation_pct = {k: v/total_value for k, v in allocation.items()}
        
        # Portföy volatilitesi (basitleştirilmiş)
        all_returns = []
        for asset in portfolio.values():
            if 'returns' in asset and asset['returns']:
                all_returns.extend(asset['returns'])
        
        portfolio_volatility = np.std(all_returns) * np.sqrt(252) if all_returns else 0
        
        # Risk profili tespiti
        detected_profile = self._detect_risk_profile(allocation_pct, portfolio_volatility)
        
        return {
            'total_value': total_value,
            'allocation': allocation_pct,
            'volatility': portfolio_volatility,
            'detected_profile': detected_profile,
            'warnings': self._generate_warnings(allocation_pct, detected_profile)
        }
    
    def _detect_risk_profile(self, allocation: Dict, volatility: float) -> str:
        """Portföy yapısından risk profilini tahmin eder"""
        crypto_ratio = allocation.get('crypto', 0)
        
        if crypto_ratio > 0.5 or volatility > 0.40:
            return 'aggressive'
        elif crypto_ratio < 0.15 and volatility < 0.20:
            return 'conservative'
        else:
            return 'moderate'
    
    def _generate_warnings(self, allocation: Dict, profile: str) -> List[str]:
        """Risk uyarıları üretir"""
        warnings = []
        profile_data = self.RISK_PROFILES[profile]
        
        crypto_ratio = allocation.get('crypto', 0)
        if crypto_ratio > profile_data['crypto_limit']:
            warnings.append(
                f"⚠️ Kripto oranı ({crypto_ratio:.1%}) {profile_data['name']} "
                f"profil için yüksek (limit: {profile_data['crypto_limit']:.1%})"
            )
        
        safe_ratio = allocation.get('commodity', 0) + allocation.get('cash', 0)
        if safe_ratio < profile_data['safe_assets_min']:
            warnings.append(
                f"⚠️ Güvenli varlık oranı ({safe_ratio:.1%}) düşük. "
                f"En az {profile_data['safe_assets_min']:.1%} önerilir."
            )
        
        # Çeşitlendirme kontrolü
        if len(allocation) < 3:
            warnings.append(
                "⚠️ Portföyünüz yeterince çeşitlendirilmemiş. "
                "En az 3 farklı varlık sınıfı önerilir."
            )
        
        return warnings
    
    def suggest_rebalancing(self, current_portfolio: Dict, 
                           target_profile: str) -> Dict:
        """
        Hedef risk profiline göre portföy dengeleme önerisi
        
        Returns:
            {
                'actions': [
                    {'action': 'reduce', 'asset': 'BTC', 'amount': 5000},
                    {'action': 'increase', 'asset': 'GC=F', 'amount': 5000}
                ],
                'reasoning': "..."
            }
        """
        target_alloc = self.RISK_PROFILES[target_profile]
        total_value = sum(asset['value'] for asset in current_portfolio.values())
        
        actions = []
        
        # Kripto kontrolü
        crypto_value = sum(
            asset['value'] for asset in current_portfolio.values() 
            if asset['type'] == 'crypto'
        )
        crypto_ratio = crypto_value / total_value
        
        if crypto_ratio > target_alloc['crypto_limit']:
            reduce_amount = crypto_value - (total_value * target_alloc['crypto_limit'])
            actions.append({
                'action': 'reduce',
                'asset_type': 'crypto',
                'amount': reduce_amount,
                'reason': 'Risk limitini aşıyor'
            })
            
            # Azalan kısmı güvenli varlıklara kaydır
            actions.append({
                'action': 'increase',
                'asset_type': 'commodity',
                'suggested_asset': 'Altın (GC=F)',
                'amount': reduce_amount,
                'reason': 'Hedge amaçlı'
            })
        
        return {
            'actions': actions,
            'reasoning': f"Portföyünüz {target_alloc['name']} profile uygun hale getirilecek"
        }
    
    def get_ai_recommendation(self, context: Dict) -> str:
        """
        Gemini AI'dan karar desteği alır
        
        Args:
            context: {
                'portfolio': {...},
                'market_condition': 'bull/bear/sideways',
                'user_question': "Ne yapmalıyım?"
            }
        """
        
        # Güvenli prompt tasarımı (hallucination önleme)
        prompt = f"""
        SEN BİR YATIRIM KARAR DESTEK ASİSTANISIN.
        
        ÖNEMLİ UYARILAR:
        - Kesin alım/satım tavsiyesi VERME
        - "Kesinlikle", "Mutlaka" gibi kelimeler KULLANMA
        - Her önerinin risklerini BELIRT
        - Sadece GENEL bilgi ver
        
        PORTFÖY DURUMU:
        {context.get('portfolio', 'Bilgi yok')}
        
        PİYASA KOŞULLARI:
        {context.get('market_condition', 'Bilinmiyor')}
        
        KULLANICI SORUSU:
        {context.get('user_question', '')}
        
        GÖREV:
        1. Mevcut durumu objektif değerlendir
        2. Alternatif senaryolar sun (en az 2 opsiyon)
        3. Her opsiyonun artı/eksi yönlerini listele
        4. Nihai kararı KULLANICIYA bırak
        
        CEVAP FORMATI:
        📊 Durum Analizi:
        [Objektif değerlendirme]
        
        💡 Opsiyon 1: [İsim]
        ✅ Artıları: ...
        ❌ Eksileri: ...
        
        💡 Opsiyon 2: [İsim]
        ✅ Artıları: ...
        ❌ Eksileri: ...
        
        🎯 Sonuç:
        [Genel tavsiye, kesin yön vermeden]
        
        ⚠️ UYARI: Bu bir AI tahminidir. Lisanslı danışman görüşü alınız.
        """
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        
        except Exception as e:
            return f"❌ AI servisi geçici olarak erişilemez durumda: {e}"
    
    def generate_exit_strategy(self, position: Dict) -> Dict:
        """
        Akıllı çıkış stratejisi üretir
        
        Args:
            position: {
                'symbol': 'BTC',
                'entry_price': 50000,
                'current_price': 95000,
                'amount': 0.5,
                'entry_date': '2024-01-15'
            }
        
        Returns:
            Kademeli satış planı
        """
        entry = position['entry_price']
        current = position['current_price']
        profit_pct = ((current - entry) / entry) * 100
        
        # Kar durumuna göre strateji
        if profit_pct > 100:
            # Çok karlı pozisyon
            strategy = {
                'type': 'aggressive_take_profit',
                'steps': [
                    {
                        'target_price': current * 1.05,
                        'sell_percentage': 50,
                        'reason': 'Ana parayı çıkar'
                    },
                    {
                        'target_price': current * 1.25,
                        'sell_percentage': 30,
                        'reason': 'Kârın büyük kısmını realize et'
                    },
                    {
                        'target_price': current * 2.0,
                        'sell_percentage': 20,
                        'reason': 'Moon bag - uzun vade için tut'
                    }
                ],
                'stop_loss': current * 0.85
            }
        
        elif profit_pct > 20:
            # Orta karlı pozisyon
            strategy = {
                'type': 'balanced_exit',
                'steps': [
                    {
                        'target_price': current * 1.10,
                        'sell_percentage': 33,
                        'reason': 'İlk kar realizasyonu'
                    },
                    {
                        'target_price': current * 1.30,
                        'sell_percentage': 33,
                        'reason': 'İkinci dalga'
                    },
                    {
                        'target_price': current * 1.50,
                        'sell_percentage': 34,
                        'reason': 'Final hedef'
                    }
                ],
                'stop_loss': entry  # Break-even
            }
        
        else:
            # Düşük/Zararlı pozisyon
            strategy = {
                'type': 'defensive',
                'recommendation': 'Pozisyonu gözden geçir',
                'stop_loss': current * 0.90,
                'warning': 'Zarardayken satış yapma. Düşüş geçici olabilir.'
            }
        
        return strategy
