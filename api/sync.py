import os
from dotenv import load_dotenv
from caldav import DAVClient
from icalendar import Calendar
import vercel_blob
from flask import Flask, jsonify

app = Flask(__name__)

# load local env
load_dotenv('.env.local')

def sync_caldav_to_blob():
    
    # Read configuration from environment variables
    caldav_url = os.environ.get("CALDAV_URL")
    caldav_username = os.environ.get("CALDAV_USERNAME")
    caldav_password = os.environ.get("CALDAV_PASSWORD")
    blob_path = os.environ.get("BLOB_PATH")
    
    # Validate BLOB_PATH is provided
    if not blob_path:
        raise ValueError("Missing required environment variable: BLOB_PATH")
    
    # Validate required environment variables
    if not all([caldav_url, caldav_username, caldav_password]):
        raise ValueError("Missing required environment variables: CALDAV_URL, CALDAV_USERNAME, CALDAV_PASSWORD")
    
    # Connect to CalDAV server
    client = DAVClient(
        url=caldav_url,
        username=caldav_username,
        password=caldav_password
    )
    
    # Get all calendars
    calendars = client.principal().calendars()
    
    # Create an integrated iCalendar
    combined_calendar = Calendar()
    combined_calendar.add('prodid', '-//CalDAV to ICS//EN')
    combined_calendar.add('version', '2.0')
    combined_calendar.add('calscale', 'GREGORIAN')
    combined_calendar.add('method', 'PUBLISH')
    
    # Collect all events from all calendars
    event_count = 0
    calendar_count = len(calendars)
    
    for calendar in calendars:
        try:
            # Get all events from this calendar
            events = calendar.events()
            
            for event in events:
                event_data = event.data
                cal = Calendar.from_ical(event_data)
                
                # Only add VEVENT components to the integrated calendar
                for component in cal.walk():
                    if component.name == 'VEVENT':
                        combined_calendar.add_component(component)
                        event_count += 1
        except Exception as e:
            print(f"Error processing calendar {calendar.name}: {str(e)}")
    
    # Convert the integrated calendar to iCalendar data
    ical_data = combined_calendar.to_ical()
    
    # Upload to Vercel Blob
    result = vercel_blob.put(blob_path, ical_data, {
                "addRandomSuffix": "false",
                "cacheControlMaxAge": "0"
            })
    
    return {
        "status": "success",
        "message": f"Successfully synchronized {event_count} events from {calendar_count} calendars"
    }

# Handler for Vercel Serverless function
@app.route("/api/sync", methods=['POST', 'GET'])
def api_sync():
    try:
        result = sync_caldav_to_blob()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500