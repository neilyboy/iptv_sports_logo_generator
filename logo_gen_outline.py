#!/usr/bin/env python3
import requests
import datetime
import os
import subprocess
import time
import sys

# --- Configuration ---
# If a date is provided via command line (e.g., 'python script.py 20251113'), use it.
if len(sys.argv) > 1:
    TARGET_DATE = sys.argv[1]
    try:
        datetime.datetime.strptime(TARGET_DATE, "%Y%m%d")
    except ValueError:
        print("Invalid date format provided. Using today's date.")
        TARGET_DATE = datetime.date.today().strftime("%Y%m%d")
else:
    TARGET_DATE = datetime.date.today().strftime("%Y%m%d")

# Define the sports and leagues to process.
LEAGUE_CONFIGS = [
    {"sport": "basketball", "league": "nba", "name": "NBA"},
    {"sport": "football", "league": "nfl", "name": "NFL"},
    {"sport": "hockey", "league": "nhl", "name": "NHL"},
    {"sport": "baseball", "league": "mlb", "name": "MLB"},
]

# Function to generate the date-stamped output directory
def get_output_dir():
    # Use the TARGET_DATE (YYYYMMDD) to create a clean directory name (YYYY-MM-DD)
    date_formatted = datetime.datetime.strptime(TARGET_DATE, "%Y%m%d").strftime("%Y-%m-%d")
    return os.path.join("game_graphics", date_formatted)

IMAGE_SIZE = "500x500" # Target final image size
# Logo size to accommodate the 5-pixel border/glow
LOGO_SIZE = "220x220" 

# --- Helper Functions ---

def get_team_info(team_data):
    """Extracts required information (name, colors, logo URL) for a team."""
    abbrev = team_data.get('abbreviation', 'TBD')
    color = "#" + team_data.get('color', 'CCCCCC').lstrip('#') 
    alt_color = "#" + team_data.get('altColor', '000000').lstrip('#')

    logo_url = None
    logos = team_data.get('logos')
    
    if logos and len(logos) > 0:
        default_logo = next((logo for logo in logos if 'default' in logo.get('rel', [])), None)
        logo_to_use = default_logo if default_logo else logos[0]
        logo_url = logo_to_use.get('href')

    if not logo_url:
        logo_url = team_data.get('logo')

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

# --- Core Logic Functions (Modified for Background Removal and Crisp Glow) ---

def get_magick_executable():
    """Determines if 'convert' or 'magick' is the correct ImageMagick command."""
    try:
        subprocess.run(['convert', '-version'], check=True, capture_output=True, text=True)
        return 'convert'
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            subprocess.run(['magick', '-version'], check=True, capture_output=True, text=True)
            return 'magick'
        except (subprocess.CalledProcessError, FileNotFoundError):
            return 'convert' 

def generate_image(away_team, home_team, raw_time_str, league_name, output_dir):
    """
    Generates the final game graphic, including background removal and a crisp, 
    shape-following white outline behind the logos.
    """
    magick_cmd = get_magick_executable()
    
    game_id = f"{away_team['abbrev']}_vs_{home_team['abbrev']}"
    output_file = os.path.join(output_dir, f"{league_name}_{game_id}.png")
    
    # Paths for temporary downloaded logos
    away_logo_dl_path = os.path.join(output_dir, f"temp_{away_team['abbrev']}_dl.png")
    home_logo_dl_path = os.path.join(output_dir, f"temp_{home_team['abbrev']}_dl.png")
    
    # Intermediate paths after resizing
    away_logo_resized_path = os.path.join(output_dir, f"temp_{away_team['abbrev']}_resized.png")
    home_logo_resized_path = os.path.join(output_dir, f"temp_{home_team['abbrev']}_resized.png")
    
    # Intermediate path after cleaning/removing white background
    away_logo_cleaned_path = os.path.join(output_dir, f"temp_{away_team['abbrev']}_cleaned.png")
    home_logo_cleaned_path = os.path.join(output_dir, f"temp_{home_team['abbrev']}_cleaned.png")
    
    # Final paths after adding the white glow/outline (THESE FILES ARE USED IN THE FINAL COMPOSITE)
    away_logo_final_path = os.path.join(output_dir, f"temp_{away_team['abbrev']}_final.png")
    home_logo_final_path = os.path.join(output_dir, f"temp_{home_team['abbrev']}_final.png")


    print(f"\nProcessing Game: {league_name}: {away_team['abbrev']} @ {home_team['abbrev']}")
    
    # 1. Download Logos
    if away_team['logo_url'] and home_team['logo_url']:
        print(f"  > Downloading logos...")
        if not download_file(away_team['logo_url'], away_logo_dl_path): return False 
        if not download_file(home_team['logo_url'], home_logo_dl_path): return False
    else:
        print(f"  > Skipping game: Logo URL(s) missing.")
        return False

    # 1.5. Resize Logos and Save
    print("  > Resizing logos...")
    try:
        # Resize: DL -> Resized
        subprocess.run([magick_cmd, away_logo_dl_path, '-resize', LOGO_SIZE, away_logo_resized_path], 
                       check=True, capture_output=True, text=True)
        
        subprocess.run([magick_cmd, home_logo_dl_path, '-resize', LOGO_SIZE, home_logo_resized_path], 
                       check=True, capture_output=True, text=True)
                       
    except subprocess.CalledProcessError as e:
        print(f"  > ERROR: Logo resizing failed. Stderr: {e.stderr}")
        return False
        
    # --- Background Removal ---
    print("  > Removing potential white background...")
    try:
        # Use fuzz to remove white pixels, making the background truly transparent
        FUZZ_LEVEL = '10%' 
        
        # Resized -> Cleaned (Removes the background, making logos ready for the glow treatment)
        subprocess.run([magick_cmd, away_logo_resized_path, 
                        '-fuzz', FUZZ_LEVEL, 
                        '-transparent', 'white', 
                        away_logo_cleaned_path],
                       check=True, capture_output=True, text=True)

        subprocess.run([magick_cmd, home_logo_resized_path, 
                        '-fuzz', FUZZ_LEVEL, 
                        '-transparent', 'white', 
                        home_logo_cleaned_path],
                       check=True, capture_output=True, text=True)
                       
    except subprocess.CalledProcessError as e:
        print(f"  > ERROR: Background removal failed. Stderr: {e.stderr}")
        return False

    # --- GLOW/OUTLINE STEP (Puts the logo back over the glow) ---
    print("  > Applying crisp white outline/glow using alpha method...")
    
    # The '3x2' setting means Radius=3, Sigma=2. Controls the width and sharpness of the glow.
    OUTLINE_BLUR = '3x2' 
    
    try:
        # AWAY TEAM GLOW (Cleaned -> Final)
        subprocess.run([
            magick_cmd, away_logo_cleaned_path, # 1. Puts Logo on stack
            '(', 
                '+clone',               # 2. Clones Logo
                '-alpha', 'extract',    # 3. Extracts alpha/silhouette
                '-fill', 'white',       # 4. Sets color to white
                '-colorize', '100%',    # 5. Makes silhouette white
                '-blur', OUTLINE_BLUR,  # 6. Blurs for glow effect
            ')', # Stack is now [Logo, Glow]
            
            '+swap', # Swap order to [Glow, Logo]
            
            '-background', 'none',
            '-compose', 'Over', # Compose Logo (top) OVER Glow (bottom)
            '-flatten', 
            away_logo_final_path
        ], check=True, capture_output=True, text=True)
        
        # HOME TEAM GLOW (Cleaned -> Final)
        subprocess.run([
            magick_cmd, home_logo_cleaned_path, # 1. Puts Logo on stack
            '(', 
                '+clone', 
                '-alpha', 'extract', 
                '-fill', 'white', 
                '-colorize', '100%', 
                '-blur', OUTLINE_BLUR, 
            ')', # Stack is now [Logo, Glow]
            
            '+swap', # Swap order to [Glow, Logo]
            
            '-background', 'none',
            '-compose', 'Over', # Compose Logo (top) OVER Glow (bottom)
            '-flatten', 
            home_logo_final_path
        ], check=True, capture_output=True, text=True)

    except subprocess.CalledProcessError as e:
        print(f"  > ERROR: Applying glow failed. Stderr: {e.stderr}")
        return False

    
    # 2. Time Formatting (Central Time Zone offset)
    try:
        dt_utc = datetime.datetime.strptime(raw_time_str, '%Y-%m-%dT%H:%MZ').replace(tzinfo=datetime.timezone.utc)
        dt_local = dt_utc - datetime.timedelta(hours=6) # UTC-6 for Central Time (CT)
        game_time_str = dt_local.strftime('%I:%M %p CT')
        if game_time_str.startswith('0'):
            game_time_str = game_time_str[1:]
    except Exception as e:
        print(f"  > Warning: Could not parse time string '{raw_time_str}'. Error: {e}")
        game_time_str = "TIME TBD"

    # 3. ImageMagick Command Construction (Diagonal Split, White Line, Logos, Text)
    command = [
        magick_cmd, 
        '-size', IMAGE_SIZE, 
        f'xc:{away_team["color"]}', 
        
        '-fill', home_team['color'],
        '-draw', 'polygon 0,500 500,0 500,500', 
        
        '-strokewidth', '4',
        '-stroke', 'white',
        '-fill', 'none',
        '-draw', 'line 5,495 495,5',
        
        # 4. Composite Logos (***CRITICAL FIX HERE: USE *_final_path***)
        # These files now contain the logo AND the crisp outline/glow behind it.
        away_logo_final_path,
        '-geometry', '+20+80', '-composite', 
        
        home_logo_final_path,
        '-geometry', '+270+200', '-composite', 
        
        # 5. Add Game Time Text Annotation
        '-pointsize', '48',
        '-font', 'Noto-Sans-Light',
        '-fill', 'white', 
        '-gravity', 'North',
        '-annotate', '+0+20', game_time_str, 
        
        output_file
    ]

    print(f"  > Generating graphic: {output_file}")
    
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"  > SUCCESS: Graphic saved to {output_file}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  > ERROR: ImageMagick command failed for {game_id}.")
        print(f"  > Stderr: {e.stderr}")
        return False
    finally:
        # Clean up all temporary logo files
        temp_files = [away_logo_dl_path, home_logo_dl_path, 
                      away_logo_resized_path, home_logo_resized_path,
                      away_logo_cleaned_path, home_logo_cleaned_path,
                      away_logo_final_path, home_logo_final_path]
        for f in temp_files:
            try:
                os.remove(f)
            except OSError: 
                pass


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

def process_league(config, base_output_dir):
    """Processes all games for a single league configuration."""
    SPORT = config['sport']
    LEAGUE = config['league']
    LEAGUE_NAME = config['name']
    
    # Create league-specific subdirectory within the date-stamped directory
    output_dir = os.path.join(base_output_dir, LEAGUE)
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
        
        raw_time_str = event.get('date')
        
        competitions = event.get('competitions', [])
        if not competitions or 'competitors' not in competitions[0]:
            continue
            
        competitors = competitions[0]['competitors']
        
        away_data = next((c['team'] for c in competitors if c['homeAway'] == 'away'), None)
        home_data = next((c['team'] for c in competitors if c['homeAway'] == 'home'), None)
        
        if not away_data or not home_data:
            continue
            
        away_team = get_team_info(away_data)
            
        home_team = get_team_info(home_data)
        
        if not all([away_team['abbrev'], away_team['color'], home_team['abbrev'], home_team['color']]):
            print(f"Skipping game due to missing required team data (abbrev or color).")
            continue
            
        if generate_image(away_team, home_team, raw_time_str, LEAGUE_NAME.lower(), output_dir):
            processed_count += 1
            
        time.sleep(0.5)
        
    print(f"\n--- {LEAGUE_NAME} Processing Finished ---")
    print(f"Successfully created {processed_count} {LEAGUE_NAME} graphic(s).")
    return processed_count

# --- Main Execution ---

def main():
    """Main function to run the process for all configured leagues."""
    
    # Get the date-stamped output directory (e.g., game_graphics/2025-11-13)
    base_output_dir = get_output_dir()
    
    # Ensure the base output directory exists
    if not os.path.exists(base_output_dir):
        os.makedirs(base_output_dir)
        print(f"Created base output directory: {base_output_dir}")

    print(f"--- Starting Script for Date: {TARGET_DATE} ---")
    
    total_processed = 0
    
    for config in LEAGUE_CONFIGS:
        total_processed += process_league(config, base_output_dir)
        
    print(f"\n--- Script Finished ---")
    print(f"Total graphics successfully generated: {total_processed}")
    print(f"Output files are in the '{base_output_dir}/' subdirectories.")


if __name__ == "__main__":
    main()
