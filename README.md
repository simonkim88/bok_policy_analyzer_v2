# BOK Policy Analyzer (한국은행 통화정책 분석기)

AI-powered monetary policy tone analysis system for the Bank of Korea's policy statements.

## Features

- **Tone Index Analysis**: Quantitative analysis of hawkish/dovish sentiment in BOK statements
- **Historical Trend Visualization**: Track policy stance changes over time
- **Interest Rate Prediction**: AI-based forecasting of future rate decisions
- **Comprehensive Dashboard**: Interactive Streamlit-based UI with McKinsey-style dark theme
- **Detailed Analysis Reports**: In-depth breakdown of each policy meeting

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/bok_policy_analyzer.git
cd bok_policy_analyzer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

## Project Structure

```
bok_policy_analyzer/
├── app.py                 # Main Streamlit application
├── requirements.txt       # Python dependencies
├── src/
│   ├── nlp/              # NLP analysis modules
│   ├── models/           # ML prediction models
│   ├── crawlers/         # Data collection scripts
│   ├── utils/            # Utility functions
│   └── views/            # UI view components
└── data/                 # Analysis data and results
```

## Technologies

- Python 3.8+
- Streamlit
- Plotly
- scikit-learn
- pandas

## License

MIT License
