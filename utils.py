import requests, base64, time, re, json
from datetime import datetime
from geopy.geocoders import Nominatim
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
import grpc
import pycountry
import pycountry_convert as pc
from decouple import config

# ─── Configuration ─────────────────────────────────────────────────────────────
OPENWEATHER_API_KEY = config('OPENWEATHER_API_KEY')
GNEWS_API_KEY       = config('GNEWS_API_KEY')
NASA_API_KEY        = config('NASA_API_KEY')
GOOGLE_API_KEY      = config('GOOGLE_API_KEY')

if not GOOGLE_API_KEY:
    raise RuntimeError("❌ GOOGLE_API_KEY not set in .env")

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("models/gemini-1.5-pro-latest")

# ─── Helpers ────────────────────────────────────────────────────────────────────

def extract_retry_delay(err, default=10):
    m = re.search(r'retry_delay\s*{\s*seconds:\s*(\d+)', str(err))
    return int(m.group(1)) if m else default


def get_gemini_analysis(prompt, temperature=0.4, top_k=40, top_p=0.9,
                        max_tokens=800, retries=5):
    print(f"[DEBUG] Gemini prompt: \n{prompt}")
    for attempt in range(1, retries+1):
        try:
            resp = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    top_k=top_k, top_p=top_p,
                    max_output_tokens=max_tokens
                )
            )
            print("[DEBUG] Gemini response received")
            print(f"[DEBUG] Raw response: {resp.text}")
            return resp.text
        except (ResourceExhausted, grpc._channel._InactiveRpcError) as e:
            delay = extract_retry_delay(e)
            print(f"[WARN] Gemini rate-limited, retrying in {delay}s (attempt {attempt})")
            time.sleep(delay)
        except Exception as e:
            print(f"[ERROR] Gemini unexpected error: {e}")
            time.sleep(default)
    print("[ERROR] Gemini failed after retries")
    return None


def get_coordinates(location, return_full_info=False):
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "json", "addressdetails": 1, "limit": 1},
            headers={"User-Agent": "DisasterIntelApp"}
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            if return_full_info:
                addr = data[0].get("address", {})
                return {"lat": lat, "lon": lon,
                        "state": addr.get("state") or addr.get("region"),
                        "country": addr.get("country")}
            return lat, lon
    except Exception as e:
        print(f"[ERROR] Geocoding failed: {e}")
    return (None, None) if not return_full_info else None


def get_weather_data(lat, lon):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        d = r.json()
        return {
            "lat": lat,
            "lon": lon,
            "temperature": f"{d['main']['temp']} °C",
            "condition": d['weather'][0]['description'],
            "humidity": f"{d['main']['humidity']}%",
            "wind": f"{d['wind']['speed']} m/s",
            "cloudiness": f"{d['clouds']['all']}%"
        }
    except Exception as e:
        print(f"[ERROR] Weather fetch failed: {e}")
        return None


def get_disaster_news(country=None, state_name=None, num_results=5):
    country_code = None
    if country:
        try:
            country_code = pycountry.countries.lookup(country).alpha_2.lower()
        except LookupError:
            country_code = None

    # Attempt to resolve subdivision name
    state_query = None
    if state_name and '-' in state_name:
        try:
            sub = next(s for s in pycountry.subdivisions if s.code.upper() == state_name.upper())
            state_query = sub.name
        except StopIteration:
            state_query = state_name
    elif state_name:
        state_query = state_name

    keywords = [
        "natural disaster", "emergency",
        "flood OR earthquake OR storm", "disaster", "natural hazard"
    ]

    for kw in keywords:
        query_parts = [kw]
        if state_query:
            query_parts.append(state_query)
        elif country:
            query_parts.append(country)

        query = ' '.join(query_parts)
        params = {
            "q": query,
            "token": GNEWS_API_KEY,
            "lang": "en",
            "max": num_results
        }
        if country_code:
            params["country"] = country_code

        try:
            resp = requests.get("https://gnews.io/api/v4/search", params=params, timeout=10)
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            if articles:
                return [
                    {
                        "title": a.get("title"),
                        "link": a.get("url"),
                        "snippet": a.get("description"),
                        "source": a.get("source", {}).get("name")
                    }
                    for a in articles
                ]
        except Exception as e:
            print(f"[WARN] GNews failed for '{query}': {e}")
    print("[ERROR] No news found.")
    return []


def get_satellite_image(lat, lon):
    try:
        assets = requests.get(
            "https://api.nasa.gov/planetary/earth/assets",
            params={"lat": lat, "lon": lon, "api_key": NASA_API_KEY}, timeout=10
        ).json().get('results', [])

        latest = (sorted(assets, key=lambda x: x['date'])[-1]['date'].split('T')[0]
                  if assets else datetime.utcnow().strftime('%Y-%m-%d'))

    except Exception:
        latest = datetime.utcnow().strftime('%Y-%m-%d')

    img_resp = requests.get(
        "https://api.nasa.gov/planetary/earth/imagery",
        params={"lat": lat, "lon": lon, "date": latest, "dim": 0.1,
                "cloud_score": False, "api_key": NASA_API_KEY}, timeout=10)

    if img_resp.headers.get('Content-Type', '').startswith('application/json'):
        meta = img_resp.json()
        url = meta.get('url')
        if not url:
            return {"base64": None, "cloud_score": None}
        img_bytes = requests.get(url, timeout=10).content
    else:
        img_bytes = img_resp.content

    return {"base64": base64.b64encode(img_bytes).decode(), "cloud_score": None}


def analyze_satellite_image(lat, lon, b64):
    if not b64:
        return "⚠️ No satellite image available."
    prompt = [{"text": f"Analyze this satellite image at lat={lat}, lon={lon}."},
              {"inline_data": {"mime_type": "image/png", "data": b64}}]
    try:
        return model.generate_content(prompt).text
    except Exception as e:
        print(f"[ERROR] Satellite analysis: {e}")
        return None


def generate_disaster_summary(weather, news_list, sat_analysis, location="Global"):
    today = datetime.utcnow().strftime("%d/%m/%Y")
    ctx = f"""
You are AIDER – AI emergency assistant.
LOCATION: {location}
DATE: {today}

🌦️ WEATHER:
- Temp: {weather.get('temperature')}
- Cond: {weather.get('condition')}
- Humidity: {weather.get('humidity')}
- Wind: {weather.get('wind')}
- Clouds: {weather.get('cloudiness')}

📰 HEADLINES:"""
    for i, a in enumerate(news_list, 1):
        ctx += f"\n{i}. {a['title']} ({a['source']}) – {a['snippet']}"
    ctx += f"""

🛰️ SATELLITE ANALYSIS:
{sat_analysis or 'No analysis.'}

🧠 TASKS:
1. Situation Summary
2. Predicted Risks
3. Areas at Risk
4. Affected Areas
5. Recommended Actions
6. Urgency Score (1–5)

Return JSON:
{{"summary":"...","risks":["..."],"affected_areas":["..."],"actions":["..."],"urgency_score":1}}"""
    return ctx


def extract_section(label, text):
    # Try to parse as JSON first
    try:
        # Try to find JSON in the text if it's not pure JSON
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            if label.lower().replace(' ', '_') in data:
                return data[label.lower().replace(' ', '_')]
    except:
        pass
    
    # Try regex pattern matching
    patterns = [
        r"\*\*"+re.escape(label)+r"\*\*(.*?)\n\s*\*\*",  # Current pattern
        r"\*\*"+re.escape(label)+r"\*\*[\s:]*(.*?)(?:\n\s*\*\*|\Z)",  # Modified pattern
        r""+re.escape(label)+r"[:\s]*(.*?)(?:\n\s*[A-Z]|\Z)",  # Simple label
    ]
    
    for pattern in patterns:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            return m.group(1).strip()
    
    return ""


def extract_list(label, text):
    # Try to parse as JSON first
    try:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            key = label.lower().replace(' ', '_')
            if key in data and isinstance(data[key], list):
                return data[key]
    except:
        pass
    
    # Try regex pattern matching
    section = extract_section(label, text)
    if not section:
        return []
    
    # Try to extract list items using various patterns
    items = []
    
    # Look for bullet points, numbers, etc.
    for line in section.splitlines():
        line = line.strip()
        if line and (line.startswith('•') or line.startswith('-') or 
                     line.startswith('*') or re.match(r'^\d+\.', line)):
            items.append(line.strip("*•-0123456789. "))
    
    # If no items found, try to split by newlines or commas
    if not items:
        if '\n' in section:
            items = [l.strip() for l in section.splitlines() if l.strip()]
        else:
            items = [i.strip() for i in section.split(',') if i.strip()]
            
    return items


def extract_score(text):
    # Try to parse as JSON first
    try:
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            if 'urgency_score' in data:
                return int(data['urgency_score'])
    except:
        pass
    
    # Try various regex patterns
    patterns = [
        r"Urgency Score.*?(\d+)",
        r"urgency_score.*?(\d+)",
        r"score.*?(\d+)\/5"
    ]
    
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return int(m.group(1))
    
    return 1


def analyze_with_gemini(weather, news, sat_img, location="Global"):
    lat, lon = weather.get("lat"), weather.get("lon")
    sat_analysis = analyze_satellite_image(lat, lon, sat_img.get("base64"))
    prompt = generate_disaster_summary(weather, news, sat_analysis, location=location)
    text = get_gemini_analysis(prompt)
    
    if not text:
        print("[ERROR] No Gemini analysis returned")
        return None
    
    print("[DEBUG] Gemini raw response:", text)
    
    # Try to parse as JSON first
    try:
        # Try to find JSON in the text if it's not pure JSON
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            # Ensure all expected fields are present
            return {
                "summary": data.get("summary", ""),
                "risks": data.get("risks", []),
                "affected_areas": data.get("affected_areas", []),
                "actions": data.get("actions", []),
                "urgency_score": int(data.get("urgency_score", 1)),
                "satellite_analysis": sat_analysis
            }
    except Exception as e:
        print(f"[WARN] JSON parsing failed: {e}")
    
    # Fall back to regex extraction if JSON parsing fails
    return {
        "summary": extract_section("Situation Summary", text),
        "risks": extract_list("Predicted Risks", text),
        "affected_areas": extract_list("Areas at Risk", text),
        "actions": extract_list("Recommended Actions", text),
        "urgency_score": extract_score(text),
        "satellite_analysis": sat_analysis
    }


def get_states(country_code):
    return [{"code": s.code, "name": s.name}
            for s in pycountry.subdivisions
            if s.country_code == country_code.upper()]


def get_all_countries():
    out = {}
    for c in pycountry.countries:
        try:
            cc = c.alpha_2
            cont = pc.country_alpha2_to_continent_code(cc)
            cname = pc.convert_continent_code_to_continent_name(cont)
            out.setdefault(cname, []).append({"name": c.name, "code": cc})
        except:
            pass
    return out