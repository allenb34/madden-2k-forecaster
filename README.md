# 🎮 Annual Sports Game Price Forecaster

A Streamlit web app that tracks and forecasts price depreciation for annual
sports game franchises (**Madden NFL** and **NBA 2K**). It fits a depreciation
curve from past editions and forecasts when the current edition will hit key
price thresholds ($49.99, $39.99, $29.99).

## Data sources

- **IsThereAnyDeal API** — historical price records (requires a free API key).
- **CheapShark API** — current deal prices (no key needed).

> Note: Both APIs track **PC digital store** prices. These are used as a free
> proxy for the depreciation *shape*; charts are labeled accordingly.

## Run locally

1. Install Python 3.11+ from https://www.python.org/downloads/
2. In this folder, install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Add your IsThereAnyDeal key to `.streamlit/secrets.toml`
   (get one at https://isthereanydeal.com/dev/app/).
4. Start the app:
   ```
   streamlit run app.py
   ```

## Deploy (free public URL)

Deployed to Streamlit Community Cloud — see deployment steps at the end of the
build. The ITAD key goes in the Streamlit Cloud "Secrets" box, not in git.

## Project layout

```
sports-price-forecaster/
├── app.py                  # Streamlit UI
├── requirements.txt        # Python dependencies
├── .gitignore              # keeps secrets out of git
├── .streamlit/
│   ├── secrets.toml        # YOUR api key (gitignored, local only)
│   └── secrets.toml.example
└── src/
    ├── config.py           # franchise & edition definitions
    ├── data_sources.py     # ITAD + CheapShark API clients  (added next)
    └── model.py            # depreciation curve fitting      (added next)
```
