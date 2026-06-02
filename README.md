# Crypto Chart API for n8n

This Render API creates TradingView-style candlestick TA chart PNGs.

## Endpoint

POST `/render-chart`

JSON body:

```json
{
  "symbol": "NEARUSDT",
  "name": "NEAR Protocol",
  "risk": "Medium",
  "reason": "Positive momentum. Wait for breakout/retest confirmation."
}
```

Response: `image/png`

## Render Deployment

1. Create a GitHub repo.
2. Upload these files.
3. Go to Render > New > Web Service.
4. Connect the repo.
5. Use:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
6. After deployment, test:
   - `https://YOUR-APP.onrender.com/`
7. Use in n8n:
   - POST `https://YOUR-APP.onrender.com/render-chart`
   - Response Format: File
   - Put Output in Field: `data`
