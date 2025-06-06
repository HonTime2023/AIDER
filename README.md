# AIDER - AI-Driven Emergency Response System

AIDER is a sophisticated web application that provides real-time disaster intelligence and emergency response recommendations using artificial intelligence. It combines multiple data sources including weather data, news, and satellite imagery to generate comprehensive emergency briefs.

## Features

- Real-time weather data analysis via OpenWeather API
- Latest disaster-related news retrieval using Serper.dev
- Satellite imagery analysis through NASA Earth API
- AI-powered analysis using Google's Gemini Pro Vision
- Dynamic location selection by continent and country
- Automatic coordinate resolution
- Manual coordinate override option
- Modern, responsive UI with dark mode support
- Caching system for improved performance

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your API keys:
   - OpenWeather API key
   - Serper.dev API key
   - NASA Earth API key
   - Google API key (Gemini Pro)

## Running the Application

1. Activate the virtual environment if not already activated
2. Run the Flask application:
   ```bash
   python app.py
   ```
3. Open a web browser and navigate to `http://localhost:5000`

## Project Structure

```
AIDER/
├── app.py              # Main Flask application
├── utils.py           # Utility functions and API integrations
├── requirements.txt   # Python dependencies
├── .env.example      # Environment variables template
├── static/           # Static assets
│   ├── css/         # Stylesheets
│   ├── js/          # JavaScript files
│   └── images/      # Images and icons
└── templates/        # HTML templates
    ├── base.html    # Base template
    └── index.html   # Main page template
```

## API Dependencies

- OpenWeather API: Weather data
- Serper.dev: News aggregation
- NASA Earth API: Satellite imagery
- Google Gemini Pro: AI analysis

## Technology Stack

- Backend: Python, Flask
- Frontend: HTML, TailwindCSS, JavaScript
- APIs: OpenWeather, Serper.dev, NASA Earth, Google Gemini
- Additional Libraries: geopy, pycountry, Pillow

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
#   A I D E R  
 