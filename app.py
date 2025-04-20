from flask import Flask, render_template, request, jsonify
from flask_caching import Cache
from utils import (
    get_states, get_coordinates,
    get_weather_data, get_disaster_news,
    get_satellite_image, get_all_countries,
    analyze_with_gemini
)

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE':'simple','CACHE_DEFAULT_TIMEOUT':300})

@app.route('/')
def index():
    countries = get_all_countries()
    return render_template('index.html', countries=countries)

@app.route('/states')
def states():
    cc = request.args.get('country')
    if not cc:
        return jsonify({'error': 'Country parameter required'}), 400
    return jsonify(get_states(cc))

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json() or {}
    country = data.get('country')
    state = data.get('state')
    loc_txt = data.get('location')
    lat = data.get('lat')
    lon = data.get('lon')

    # Handle lat/lon fallback properly
    if lat in [None, '', 'null'] or lon in [None, '', 'null']:
        coords = get_coordinates(loc_txt or state or country, return_full_info=True)
        if not coords:
            return jsonify({'error': 'Could not determine coordinates'}), 404
        lat, lon = coords['lat'], coords['lon']
        state = state or coords.get('state')
        country = country or coords.get('country')
    else:
        try:
            lat, lon = float(lat), float(lon)
        except:
            return jsonify({'error': 'Invalid lat/lon format'}), 400

    # Fetch external data
    weather = get_weather_data(lat, lon) or {}
    news = get_disaster_news(country=country, state_name=state) or []
    sat_img = get_satellite_image(lat, lon) or {"base64": None}

    # Run Gemini analysis
    summary_loc = loc_txt or (f"{state}, {country}" if state else country)
    analysis = analyze_with_gemini(weather, news, sat_img, location=summary_loc)

    if not analysis:
        return jsonify({'error': 'Analysis failed'}), 500

    # Merge everything
    return jsonify({
        **analysis,
        "weather": weather,
        "news": news
    })

if __name__ == '__main__':
    app.run(debug=True)
