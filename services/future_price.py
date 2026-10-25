import yfinance as yf
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

def predict_probability(symbol="BTC-USD", target_price=100000, days=10):
    """
    Calculates the probability of the symbol reaching the target price within the given days.
    Returns a dictionary with the results.
    """
    result = {
        "success": False,
        "message": "",
        "current_price": 0,
        "target_price": target_price,
        "days": days,
        "probability": 0,
        "accuracy": 0,
        "feature_importances": {},
        "required_increase": 0
    }

    try:
        # --- 2. VERİ ÇEKME ---
        # ATH'yi doğru bulmak için 'max' (tüm zamanlar) periyodunu çekiyoruz
        df = yf.download(symbol, period="max", interval="1d", progress=False)

        if df.empty:
            result["message"] = "Veri çekilemedi."
            return result

        # yfinance returns MultiIndex columns sometimes (Price, Ticker). We need to flatten if necessary.
        # But usually for single ticker it's fine. Let's ensure 'Close' exists.
        if isinstance(df.columns, pd.MultiIndex):
             # If columns are MultiIndex (e.g. ('Close', 'BTC-USD')), drop level 1
             df.columns = df.columns.droplevel(1)

        # En güncel kapanış
        guncel_fiyat = float(df['Close'].iloc[-1])
        result["current_price"] = guncel_fiyat

        # Gereken yükseliş oranı
        if target_price <= guncel_fiyat:
            result["success"] = True
            result["probability"] = 1.0
            result["message"] = "Fiyat zaten hedefin üzerinde!"
            return result
        else:
            gereken_artis_orani = (target_price - guncel_fiyat) / guncel_fiyat
            result["required_increase"] = gereken_artis_orani

        # --- 3. ÖZELLİK MÜHENDİSLİĞİ (Gelişmiş) ---
        # Temel değişimler
        df['Getiri'] = df['Close'].pct_change()
        df['Volatilite'] = df['Getiri'].rolling(window=7).std()

        # YENİ: Drawdown (Zirveden Uzaklık)
        df['Running_Max'] = df['High'].cummax()
        df['Drawdown'] = (df['Close'] / df['Running_Max']) - 1

        # YENİ: Hedefe Uzaklık (Target Proximity)
        df['Hedefe_Yakinlik'] = (target_price - df['Close']) / df['Close']

        # Ortalamalar ve Momentum
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['Trend_Gucu'] = (df['SMA_20'] - df['SMA_50']) / df['SMA_50']

        # --- 4. ETİKETLEME (TARGET) ---
        # Gelecek VADE_GUN içindeki en yüksek fiyat hedefe değdi mi?
        indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=days)
        df['Gelecek_Max'] = df['High'].rolling(window=indexer).max()

        # Mantık: Gelecekteki En Yüksek Fiyat >= (Şu anki Fiyat + Gereken Artış)
        df['Target'] = (df['Gelecek_Max'] >= df['Close'] * (1 + gereken_artis_orani)).astype(int)

        # NaN temizliği
        df.dropna(inplace=True)

        if len(df) < 200:
             result["message"] = "Yetersiz veri (en az 200 gün gerekli)."
             return result

        # --- 5. MODEL EĞİTİMİ ---
        features = ['Getiri', 'Volatilite', 'Drawdown', 'Trend_Gucu', 'Hedefe_Yakinlik']
        X = df[features]
        y = df['Target']

        # Son 200 günü test için ayıralım
        test_size = 200
        if len(df) > test_size + 50:
            X_train = X.iloc[:-test_size]
            y_train = y.iloc[:-test_size]
            X_test = X.iloc[-test_size:]
            y_test = y.iloc[-test_size:]
        else:
            # Veri azsa standart split
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

        model = XGBClassifier(n_estimators=200, learning_rate=0.02, max_depth=5, eval_metric='logloss')
        model.fit(X_train, y_train)

        # --- 6. SONUÇ ---
        # Modelin başarısı
        acc = accuracy_score(y_test, model.predict(X_test))
        result["accuracy"] = acc

        # Tahmin
        son_veri = X.iloc[[-1]]
        olasilik = model.predict_proba(son_veri)[0][1]
        result["probability"] = float(olasilik)

        # Hangi veri daha etkili oldu?
        imps = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
        result["feature_importances"] = imps.to_dict()

        result["success"] = True
        return result

    except Exception as e:
        result["message"] = str(e)
        return result

if __name__ == "__main__":
    # Test run
    print("Testing module...")
    res = predict_probability()
    print(res)
