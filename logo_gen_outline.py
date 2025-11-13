#!/usr/bin/env python3
import requests
import datetime
import os
import subprocess
import time
import shutil
import sys

# --- Configuration ---
# Set the date for the schedule. Defaults to today's date.
# Format: YYYYMMDD
# Can be overridden by command-line argument: python3 logo_gen.py 20251115
if len(sys.argv) > 1:
    TARGET_DATE = sys.argv[1]
    # Validate the date format
    try:
        datetime.datetime.strptime(TARGET_DATE, "%Y%m%d")
    except ValueError:
        print(f"ERROR: Invalid date format '{TARGET_DATE}'. Please use YYYYMMDD format (e.g., 20251115)")
        sys.exit(1)
else:
    TARGET_DATE = datetime.date.today().strftime("%Y%m%d")

# Define the sports and leagues to process.
# To process ALL these, ensure your main execution loop iterates over this list.
# The script defaults to running ALL defined configurations below.
LEAGUE_CONFIGS = [
    {"sport": "basketball", "league": "nba", "name": "NBA"},
    {"sport": "football", "league": "nfl", "name": "NFL"},
    {"sport": "hockey", "league": "nhl", "name": "NHL"},
    {"sport": "baseball", "league": "mlb", "name": "MLB"},
]

BASE_OUTPUT_DIR = os.path.join("game_graphics", TARGET_DATE)
IMAGE_SIZE = "500x500" # Target final image size
LOGO_SIZE = "200x200" # Size to which the downloaded logos will be resized

# --- Helper Functions (No Change) ---

def get_team_info(team_data):
    """Extracts required information (name, colors, logo URL) for a team."""
    abbrev = team_data.get('abbreviation', 'TBD')
    # Remove the initial '#' from color codes if they exist (sometimes the API provides them, sometimes not)
    color = "#" + team_data.get('color', 'CCCCCC').lstrip('#')  # Default to gray if color missing
    alt_color = "#" + team_data.get('altColor', '000000').lstrip('#') # Secondary color for border/text

    logo_url = None
    logos = team_data.get('logos')
    
    # 1. Check the preferred 'logos' list structure
    if logos and len(logos) > 0:
        # Prioritize the logo marked as 'default' if possible, otherwise take the first one.
        default_logo = next((logo for logo in logos if 'default' in logo.get('rel', [])), None)
        logo_to_use = default_logo if default_logo else logos[0]
        logo_url = logo_to_use.get('href')

    # 2. Add fallback check for a simple 'logo' key which sometimes holds the URL string
    if not logo_url:
        logo_url = team_data.get('logo') # Check for single logo URL string

    return {
        'abbrev': abbrev,
        'color': color,
        'alt_color': alt_color,
        'logo_url': logo_url
    }

def download_file(url, local_path):
    """Downloads a file from a URL to a local path."""
    try:
        response = requests.get(url, stream=True, timeout=10)
        response.raise_for_status()
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        print(f"  > ERROR: Failed to download {url}. {e}")
        return False

# --- Core Logic Functions (Modified) ---

def add_glow_to_logo(logo_path, output_path):
    """
    Adds a white glow effect around a logo using ImageMagick.
    The glow follows the contours of the logo using its alpha channel.
    Returns True on success, False on failure.
    """
    try:
        # ImageMagick command to add white glow:
        # 1. Clone the image and extract alpha channel
        # 2. Blur the alpha to create glow effect
        # 3. Colorize the glow white
        # 4. Composite original logo on top
        command = [
            'convert',
            logo_path,
            # Create the glow layer
            '(',
            '+clone',                      # Clone the image
            '-background', 'white',        # Set background to white
            '-shadow', '100x5+0+0',        # Create shadow (used for glow)
            ')',
            # Apply additional blur for softer glow
            '(',
            '+clone',
            '-background', 'white',
            '-shadow', '100x3+0+0',
            ')',
            # Composite: glow layers under the original
            '-reverse',
            '-background', 'none',
            '-layers', 'merge',
            '+repage',
            output_path
        ]
        
        subprocess.run(command, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  > Warning: Failed to add glow to logo. {e.stderr}")
        # If glow fails, copy original file as fallback
        shutil.copy2(logo_path, output_path)
        return False

def generate_image(away_team, home_team, raw_time_str, league_name, output_dir):
    """
    Generates the final diagonal split, white-bordered game graphic with game time
    using ImageMagick. Returns True on success, False on failure.
    """
    game_id = f"{away_team['abbrev']}_vs_{home_team['abbrev']}"
    output_file = os.path.join(output_dir, f"{league_name}_{game_id}.png")
    
    # Paths for temporary downloaded logos
    away_logo_path = os.path.join(output_dir, f"temp_{away_team['abbrev']}_logo.png")
    home_logo_path = os.path.join(output_dir, f"temp_{home_team['abbrev']}_logo.png")
    
    # Paths for logos with glow effect applied
    away_logo_glow_path = os.path.join(output_dir, f"temp_{away_team['abbrev']}_logo_glow.png")
    home_logo_glow_path = os.path.join(output_dir, f"temp_{home_team['abbrev']}_logo_glow.png")

    print(f"\nProcessing Game: {league_name}: {away_team['abbrev']} @ {home_team['abbrev']}")
    
    # 1. Download Logos
    if away_team['logo_url'] and home_team['logo_url']:
        print(f"  > Downloading logos...")
        if not download_file(away_team['logo_url'], away_logo_path):
            print(f"  > Skipping game {game_id} due to away logo download failure.")
            return False 
        if not download_file(home_team['logo_url'], home_logo_path):
            print(f"  > Skipping game {game_id} due to home logo download failure.")
            try: os.remove(away_logo_path)
            except OSError: pass
            return False
    else:
        print(f"  > Skipping game: Logo URL(s) missing from API data (Away URL: {'Present' if away_team['logo_url'] else 'Missing'}, Home URL: {'Present' if home_team['logo_url'] else 'Missing'}).")
        return False

    # 2. Apply white glow effect to logos
    print(f"  > Adding white glow to logos...")
    add_glow_to_logo(away_logo_path, away_logo_glow_path)
    add_glow_to_logo(home_logo_path, home_logo_glow_path)

    # 3. Time Formatting
    try:
        # Assuming ISO format like 2025-11-12T00:00Z. Parse as UTC.
        dt_utc = datetime.datetime.strptime(raw_time_str, '%Y-%m-%dT%H:%MZ').replace(tzinfo=datetime.timezone.utc)
        
        # Adjusting to Central Time (CT). UTC-6 offset.
        # This assumes no daylight savings time adjustment, which is acceptable for a daily sports schedule.
        dt_local = dt_utc - datetime.timedelta(hours=6) 
        game_time_str = dt_local.strftime('%I:%M %p CT')
        # Remove leading zero for cleaner time display (e.g., '07:30 PM' -> '7:30 PM')
        if game_time_str.startswith('0'):
            game_time_str = game_time_str[1:]
    except Exception as e:
        print(f"  > Warning: Could not parse time string '{raw_time_str}'. Error: {e}")
        game_time_str = "TIME TBD"

    # 4. ImageMagick Command Construction (Diagonal Split and White Line)

    # Logo X positions remain centered in their 250px halves: Away +25, Home +275
    # Logo Y positions adjusted for increased visual separation from the diagonal line:
    # Away (Top-Right Quadrant): Moved UP 60px: 150 -> +90
    # Home (Bottom-Left Quadrant): Moved DOWN 60px: 150 -> +210
    
    command = [
        'convert', 
        '-size', IMAGE_SIZE, 
        
        # 1. Create the base canvas (Away Team Color, covering the Top-Right portion)
        f'xc:{away_team["color"]}', 
        
        # 2. Draw the Home Team's color (Bottom-Left triangle)
        # Polygon points: (0, 500) bottom-left, (500, 0) top-right, (500, 500) bottom-right
        '-fill', home_team['color'],
        '-draw', 'polygon 0,500 500,0 500,500', 
        
        # 3. Draw the white diagonal dividing line (4px stroke)
        # Line from (5, 495) to (495, 5) to create a centered white line
        '-strokewidth', '4',
        '-stroke', 'white',
        '-fill', 'none',
        '-draw', 'line 5,495 495,5',
        
        # 4. Composite Logos (with glow effect)
        # Away Logo (Top-Right area) -> Y moved to +90
        '(', away_logo_glow_path, '-resize', LOGO_SIZE, ')',
        '-geometry', '+25+90', '-composite', 
        
        # Home Logo (Bottom-Left area) -> Y moved to +210
        '(', home_logo_glow_path, '-resize', LOGO_SIZE, ')',
        '-geometry', '+275+210', '-composite',
        
        # 5. Add Game Time Text Annotation
        '-pointsize', '48',
        '-font', 'Noto-Sans-Light', # Attempt to use a lighter weight font
        '-fill', 'white', 
        '-gravity', 'North',
        '-annotate', '+0+20', game_time_str, 
        
        # 6. Final Output
        output_file
    ]

    print(f"  > Generating graphic: {output_file}")
    
    try:
        # Check if the desired font (Noto-Sans-Light) is available; if not, fall back to a generic sans-serif
        font_check_command = ['identify', '-list', 'font', 'Noto-Sans-Light']
        result = subprocess.run(font_check_command, capture_output=True, text=True)
        if result.returncode != 0:
             # Fallback to a common, less bold sans-serif
            command[13] = 'sans-serif' 
        
        subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"  > SUCCESS: Graphic saved to {output_file}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  > ERROR: ImageMagick command failed for {game_id}.")
        print(f"  > Stderr: {e.stderr}")
        return False
    finally:
        # Clean up temporary logo files
        for temp_file in [away_logo_path, home_logo_path, away_logo_glow_path, home_logo_glow_path]:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except OSError as e:
                print(f"  > Warning: Could not remove temporary file {temp_file}. {e}")

def fetch_schedule(sport, league):
    """Fetches the daily scoreboard data for a specific sport/league."""
    api_url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates={TARGET_DATE}"
    print(f"Fetching schedule for {league.upper()} on {TARGET_DATE} from: {api_url}")
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching API data for {league.upper()}: {e}")
        return None

def process_league(config):
    """Processes all games for a single league configuration."""
    SPORT = config['sport']
    LEAGUE = config['league']
    LEAGUE_NAME = config['name']
    
    # Create league-specific output directory
    output_dir = os.path.join(BASE_OUTPUT_DIR, LEAGUE)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    data = fetch_schedule(SPORT, LEAGUE)
    
    if not data or 'events' not in data:
        print(f"No game data found for {LEAGUE_NAME}. Skipping.")
        return 0

    total_games = len(data['events'])
    print(f"\nFound {total_games} games for {LEAGUE_NAME}.")
    
    processed_count = 0
    for event in data['events']:
        
        # Extract the UTC time string for display
        raw_time_str = event.get('date')
        
        # API structure check
        competitions = event.get('competitions', [])
        if not competitions or 'competitors' not in competitions[0]:
            print(f"Skipping event {event.get('id', 'N/A')}: No competition data found.")
            continue
            
        competitors = competitions[0]['competitors']
        
        away_data = next((c['team'] for c in competitors if c['homeAway'] == 'away'), None)
        home_data = next((c['team'] for c in competitors if c['homeAway'] == 'home'), None)
        
        if not away_data or not home_data:
            print(f"Skipping event {event.get('id', 'N/A')}: Could not identify both home and away teams.")
            continue
            
        away_team = get_team_info(away_data)
        home_team = get_team_info(home_data)
        
        # Check for minimum required info
        if not all([away_team['abbrev'], away_team['color'], home_team['abbrev'], home_team['color']]):
            print(f"Skipping game due to missing required team data (abbrev or color).")
            continue
            
        if generate_image(away_team, home_team, raw_time_str, LEAGUE_NAME.lower(), output_dir):
            processed_count += 1
            
        time.sleep(0.5) # Be kind to the API endpoints
        
    print(f"\n--- {LEAGUE_NAME} Processing Finished ---")
    print(f"Successfully created {processed_count} {LEAGUE_NAME} graphic(s).")
    return processed_count

# --- Main Execution ---

def main():
    """Main function to run the process for all configured leagues."""
    
    print(f"=== Processing games for date: {TARGET_DATE} ===\n")
    
    # Ensure the base output directory exists
    if not os.path.exists(BASE_OUTPUT_DIR):
        os.makedirs(BASE_OUTPUT_DIR)
        print(f"Created base output directory: {BASE_OUTPUT_DIR}")

    total_processed = 0
    
    for config in LEAGUE_CONFIGS:
        total_processed += process_league(config)
        
    print(f"\n--- Script Finished ---")
    print(f"Total graphics successfully generated across all leagues: {total_processed}")
    print(f"Output files are in the '{BASE_OUTPUT_DIR}/' subdirectories.")


if __name__ == "__main__":
    main()
