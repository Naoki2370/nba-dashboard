import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
from nba_api.stats.endpoints import scoreboardv3, leaguestandings, leagueleaders
from nba_api.live.nba.endpoints import boxscore
from nba_api.stats.static import teams
import re
import time


API_TIMEOUT = 30  # 秒

def api_call_with_retry(func, max_retries=2, *args, **kwargs):
    """NBA API 呼び出しをリトライ付きで実行する。"""
    for attempt in range(max_retries):
        try:
            time.sleep(0.6)  # DDOS対策: APIコール間隔をあける (キャッシュミス時のみ実行される)
            return func(*args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1秒, 2秒
                time.sleep(wait_time)
            else:
                raise e

st.set_page_config(page_title="NBA Stats Dashboard", layout="wide", page_icon="🏀")

st.title("🏀 NBA Stats Dashboard")

# CSS Customization
st.markdown("""
<style>
div.css-1r6slb0.e1tzin5v2 {
    background-color: #2b2b2b;
    border-radius: 10px;
    padding: 10px;
    margin-bottom: 10px;
}
.card {
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 15px;
    margin-bottom: 15px;
    box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
}
.game-time {
    text-align: center;
    color: #888;
    font-size: 0.9em;
    margin-top: -5px;
}
</style>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📅 今日の試合情報一覧", "🏆 順位・個人成績"])

# Helper functions
def get_jst_today():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    return now.date()

def date_to_api_format(d):
    return d.strftime("%Y-%m-%d")

def get_logo_url(team_id):
    return f"https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.svg"

def get_headshot_url(player_id):
    return f"https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"

def convert_et_to_jst(time_text):
    """GAME_STATUS_TEXT の時刻文字列 (例: '7:30 PM ET') を JST に変換する。
    時刻形式でない場合 (例: 'Final') はそのまま返す。"""
    match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)\s*ET', time_text.strip(), re.IGNORECASE)
    if not match:
        return time_text.strip()
    
    hour = int(match.group(1))
    minute = int(match.group(2))
    ampm = match.group(3).upper()
    
    # 12時間制 → 24時間制
    if ampm == 'AM' and hour == 12:
        hour = 0
    elif ampm == 'PM' and hour != 12:
        hour += 12
    
    # ET → JST (+14時間)
    et_tz = pytz.timezone('US/Eastern')
    jst_tz = pytz.timezone('Asia/Tokyo')
    
    # 仮の日付で datetime を作成（日付をまたぐ計算のため）
    dummy_date = datetime(2025, 1, 1, hour, minute)
    et_time = et_tz.localize(dummy_date)
    jst_time = et_time.astimezone(jst_tz)
    
    return f"{jst_time.hour}:{jst_time.minute:02d} JST"

def get_game_time_display(status_text, game_status_id):
    """試合ステータスに応じた表示文字列を返す。
    game_status_id: 1=未開始, 2=進行中, 3=終了"""
    if game_status_id == 3:
        return "Final"
    elif game_status_id == 2:
        return "🔴 Live"
    else:
        # 未開始の場合、時刻を JST に変換
        jst_time = convert_et_to_jst(status_text)
        return jst_time

# Caching API Calls
@st.cache_data(ttl=600)
def get_scoreboard(date_str):
    def _fetch():
        board = scoreboardv3.ScoreboardV3(game_date=date_str, timeout=API_TIMEOUT)
        return board.game_header.get_data_frame(), board.line_score.get_data_frame()
    return api_call_with_retry(_fetch)

@st.cache_data(ttl=600)
def get_boxscore(game_id):
    def _fetch():
        b = boxscore.BoxScore(game_id, timeout=API_TIMEOUT)
        d = b.get_dict()['game']
        players = d['homeTeam']['players'] + d['awayTeam']['players']
        records = []
        for p in players:
            s = p.get('statistics', {})
            # parse PT29M06.70S format
            minutes_raw = s.get('minutes', 'PT00M00.00S')
            try:
                if 'M' in minutes_raw:
                    parts = minutes_raw.replace('PT','').replace('S','').split('M')
                    mins = parts[0]
                    secs = parts[1].split('.')[0] if len(parts)>1 else '00'
                    minutes = f"{int(mins)}:{int(float(secs)):02d}"
                else:
                    minutes = "0:00"
            except:
                minutes = "0:00"

            rec = {
                'teamId': d['homeTeam']['teamId'] if p in d['homeTeam']['players'] else d['awayTeam']['teamId'],
                'firstName': p.get('firstName', ''),
                'familyName': p.get('familyName', ''),
                'personId': p.get('personId', ''),
                'jerseyNum': p.get('jerseyNum', ''),
                'position': p.get('position', ''),
                'minutes': minutes,
                'fieldGoalsMade': s.get('fieldGoalsMade', 0),
                'fieldGoalsAttempted': s.get('fieldGoalsAttempted', 0),
                'fieldGoalsPercentage': s.get('fieldGoalsPercentage', 0.0),
                'threePointersMade': s.get('threePointersMade', 0),
                'threePointersAttempted': s.get('threePointersAttempted', 0),
                'threePointersPercentage': s.get('threePointersPercentage', 0.0),
                'freeThrowsMade': s.get('freeThrowsMade', 0),
                'freeThrowsAttempted': s.get('freeThrowsAttempted', 0),
                'freeThrowsPercentage': s.get('freeThrowsPercentage', 0.0),
                'reboundsOffensive': s.get('reboundsOffensive', 0),
                'reboundsDefensive': s.get('reboundsDefensive', 0),
                'reboundsTotal': s.get('reboundsTotal', 0),
                'assists': s.get('assists', 0),
                'steals': s.get('steals', 0),
                'blocks': s.get('blocks', 0),
                'turnovers': s.get('turnovers', 0),
                'foulsPersonal': s.get('foulsPersonal', 0),
                'points': s.get('points', 0),
                'plusMinusPoints': s.get('plusMinusPoints', 0.0)
            }
            records.append(rec)
        return pd.DataFrame(records)
        
    # Rate Limitが無い静的JSON CDNから取得するため、DDOS対策(0.6s Sleep)を持ったapi_call_with_retryは使わない
    for attempt in range(2):
        try:
            return _fetch()
        except Exception:
            if attempt == 1:
                return pd.DataFrame()
            time.sleep(1)

@st.cache_data(ttl=600)
def get_standings():
    def _fetch():
        standings = leaguestandings.LeagueStandings(timeout=API_TIMEOUT)
        return standings.standings.get_data_frame()
    return api_call_with_retry(_fetch)

@st.cache_data(ttl=600)
def get_leaders(per_mode):
    def _fetch():
        leaders = leagueleaders.LeagueLeaders(per_mode48=per_mode, timeout=API_TIMEOUT)
        return leaders.league_leaders.get_data_frame()
    return api_call_with_retry(_fetch)

# NBA Teams List
nba_teams = [team['full_name'] for team in teams.get_teams()]
nba_teams.sort()

# --- ボックススコア整形関数（ループ外で定義） ---
def format_boxscore(df, team_id):
    tdf = df[df['teamId'] == team_id].copy()
    tdf['PLAYER_NAME'] = tdf['firstName'] + " " + tdf['familyName']
    
    # Identify starters and extract position
    tdf['is_starter'] = tdf['position'].apply(lambda x: pd.notna(x) and str(x).strip() != "")
    tdf['POS'] = tdf['position'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() != "" else "")
    # Use jerseyNum natively grabbed from CDN instead of heavy get_roster mapping
    tdf['NO.'] = tdf['jerseyNum'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() != 'None' else "")
        
    # Add Player Headshot URL
    tdf['Photo'] = tdf['personId'].apply(get_headshot_url)
    
    # Rename columns to match requirements
    rename_dict = {
        'minutes': 'MIN', 'points': 'PTS', 'reboundsTotal': 'REB', 'assists': 'AST', 
        'steals': 'STL', 'blocks': 'BLK',
        'fieldGoalsMade': 'FGM', 'fieldGoalsAttempted': 'FGA', 'fieldGoalsPercentage': 'FG%',
        'threePointersMade': '3PM', 'threePointersAttempted': '3PA', 'threePointersPercentage': '3P%',
        'freeThrowsMade': 'FTM', 'freeThrowsAttempted': 'FTA', 'freeThrowsPercentage': 'FT%',
        'plusMinusPoints': '+/-'
    }
    tdf = tdf.rename(columns=rename_dict)
    
    # Ensure column order
    cols = ['NO.', 'Photo', 'PLAYER_NAME', 'POS', 'MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 
            'FGM', 'FGA', 'FG%', '3PM', '3PA', '3P%', 'FTM', 'FTA', 'FT%', '+/-', 'is_starter']
    
    # Only keep columns that exist
    cols = [c for c in cols if c in tdf.columns]
    tdf = tdf[cols]
    
    # スターターをハイライトするためのデータを事前に取得
    starter_flags = tdf['is_starter'].tolist()
    
    # Styling function to bold starters and add bottom border to the last starter
    def highlight_starters(row):
        idx = row.name
        try:
            row_loc = tdf.index.get_loc(idx)
        except Exception:
            return [''] * len(row)
        
        is_starter = starter_flags[row_loc]
        next_is_starter = starter_flags[row_loc + 1] if row_loc < len(starter_flags) - 1 else False
            
        styles = [''] * len(row)
        if is_starter:
            styles = ['font-weight: bold'] * len(row)
            # If this is the last starter, add a border
            if not next_is_starter:
                styles = [s + '; border-bottom: 2px solid #888888 !important;' for s in styles]
        return styles
    
    # Drop the helper col before display
    row_count = len(tdf)
    styled_df = tdf.drop(columns=['is_starter']).style.apply(highlight_starters, axis=1).hide(axis="index")
    # Format percentages and floats
    format_dict = {
        'FG%': '{:.1%}', '3P%': '{:.1%}', 'FT%': '{:.1%}', '+/-': '{:+.0f}'
    }
    styled_df = styled_df.format(formatter={k: v for k, v in format_dict.items() if k in tdf.columns}, na_rep="")
    
    return styled_df, row_count

with tab1:
    st.header("試合情報一覧")
    
    if 'current_date' not in st.session_state:
        st.session_state.current_date = get_jst_today()
        
    col1, col2, col3, col4, col5 = st.columns([1, 4, 1, 1, 1.5])
    
    with col1:
        if st.button("◀ 前日"):
            st.session_state.current_date -= timedelta(days=1)
            
    with col2:
        selected_date = st.date_input("日付を選択", value=st.session_state.current_date)
        if selected_date != st.session_state.current_date:
            st.session_state.current_date = selected_date
            
    with col3:
        if st.button("翌日 ▶"):
            st.session_state.current_date += timedelta(days=1)
            
    with col4:
        if st.button("今日に戻る"):
            st.session_state.current_date = get_jst_today()
            st.rerun()
            
    with col5:
        if st.button("🔄 データを更新"):
            # 試合情報のキャッシュのみクリア（順位表・個人成績・ロスターはキャッシュを維持）
            get_scoreboard.clear()
            st.rerun()

    favorite_teams = st.multiselect(
        "お気に入りチームを選択（上位に表示）", 
        options=nba_teams,
        default=["Los Angeles Lakers", "Charlotte Hornets"]
    )
    
    # 日本時間(JST)のその日に行われる試合は、米国東部時間(ET)では前日の日付で管理されているため、
    # -1日してAPIにリクエストします。
    # 理由: JST = ET + 14時間。JST の1日 (00:00-23:59) は ET では前日10:00〜当日09:59に対応。
    # NBA の試合は通常 ET の正午以降に開催されるため、-1日で正しく取得できます。
    # (ロンドンゲーム等の早朝開催は例外となる可能性があります)
    api_date_query = date_to_api_format(st.session_state.current_date - timedelta(days=1))
    display_date = st.session_state.current_date.strftime("%Y/%m/%d")
    
    st.subheader(f"{display_date} (日本時間) の試合")
    
    try:
        games_df, linescores = get_scoreboard(api_date_query)
        
        if games_df.empty:
            st.info("この日の試合はありません。")
        else:
            games_list = []
            for _, game in games_df.iterrows():
                game_id = game['gameId']
                game_status_id = int(game.get('gameStatus', 1))
                game_status_text = str(game.get('gameStatusText', ''))
                
                # V3: LineScore は gameId でフィルタし、1行目=ホーム、2行目=アウェイ
                game_lines = linescores[linescores['gameId'] == game_id]
                if len(game_lines) < 2:
                    continue
                
                home_team_data = game_lines.iloc[0]
                visitor_team_data = game_lines.iloc[1]
                
                home_team_id = home_team_data['teamId']
                visitor_team_id = visitor_team_data['teamId']
                
                h_city = home_team_data.get('teamCity', '')
                h_name = home_team_data.get('teamName', '')
                home_full_name = f"{h_city} {h_name}".strip()
                home_team_abbr = home_team_data.get('teamTricode', 'Home')
                
                v_city = visitor_team_data.get('teamCity', '')
                v_name = visitor_team_data.get('teamName', '')
                visitor_full_name = f"{v_city} {v_name}".strip()
                visitor_team_abbr = visitor_team_data.get('teamTricode', 'Visitor')
                
                # 未開始試合はスコアを "-" 表示
                if game_status_id == 1:
                    home_pts = "-"
                    visitor_pts = "-"
                else:
                    home_pts = home_team_data.get('score', '-')
                    visitor_pts = visitor_team_data.get('score', '-')
                    # score が None/NaN の場合のガード
                    if pd.isna(home_pts):
                        home_pts = "-"
                    if pd.isna(visitor_pts):
                        visitor_pts = "-"
                    # 数値の場合は整数に変換
                    try:
                        home_pts = int(home_pts)
                    except (ValueError, TypeError):
                        pass
                    try:
                        visitor_pts = int(visitor_pts)
                    except (ValueError, TypeError):
                        pass
                
                is_favorite = False
                if home_full_name in favorite_teams or visitor_full_name in favorite_teams:
                    is_favorite = True
                
                # 試合開始時刻を JST で取得
                time_display = get_game_time_display(game_status_text, game_status_id)
                    
                games_list.append({
                    'game_id': game_id,
                    'home_id': home_team_id,
                    'visitor_id': visitor_team_id,
                    'home_abbr': home_team_abbr,
                    'visitor_abbr': visitor_team_abbr,
                    'home_full': home_full_name,
                    'visitor_full': visitor_full_name,
                    'home_pts': home_pts,
                    'visitor_pts': visitor_pts,
                    'is_favorite': is_favorite,
                    'game_status_id': game_status_id,
                    'time_display': time_display
                })
            
            games_list.sort(key=lambda x: x['is_favorite'], reverse=True)
            
            for g in games_list:
                with st.container(border=True):
                    
                    # Layout with logos and centered score
                    c1, c2, c3, c4, c5 = st.columns([1, 3, 2, 3, 1])
                    with c1:
                        st.image(get_logo_url(g['visitor_id']), width=50)
                    with c2:
                        st.markdown(f"<h3 style='text-align: right; margin-top: 10px;'>{g['visitor_full']}</h3>", unsafe_allow_html=True)
                    with c3:
                        st.markdown(f"<h2 style='text-align: center; margin-top: 5px;'>{g['visitor_pts']} - {g['home_pts']}</h2>", unsafe_allow_html=True)
                        # 試合開始時刻 or ステータスを表示
                        st.markdown(f"<p class='game-time'>{g['time_display']}</p>", unsafe_allow_html=True)
                    with c4:
                        st.markdown(f"<h3 style='text-align: left; margin-top: 10px;'>{g['home_full']}</h3>", unsafe_allow_html=True)
                    with c5:
                        st.image(get_logo_url(g['home_id']), width=50)
                    
                    # 未開始試合はボックススコアを表示しない
                    if g['game_status_id'] != 1:
                        with st.expander("ボックススコアを見る"):
                            try:
                                player_stats = get_boxscore(g['game_id'])
                                
                                if not player_stats.empty:
                                    st.write(f"**{g['visitor_full']} Stats**")
                                    styled_visitor, visitor_row_count = format_boxscore(player_stats, g['visitor_id'])
                                    # 行数に基づいて高さを動的計算（1行≒35px + ヘッダー50px + マージン20px）
                                    visitor_height = visitor_row_count * 35 + 70
                                    st.dataframe(
                                        styled_visitor, 
                                        use_container_width=True, 
                                        hide_index=True,
                                        height=visitor_height,
                                        column_config={"Photo": st.column_config.ImageColumn("Photo")}
                                    )
                                    
                                    st.write(f"**{g['home_full']} Stats**")
                                    styled_home, home_row_count = format_boxscore(player_stats, g['home_id'])
                                    home_height = home_row_count * 35 + 70
                                    st.dataframe(
                                        styled_home, 
                                        use_container_width=True, 
                                        hide_index=True,
                                        height=home_height,
                                        column_config={"Photo": st.column_config.ImageColumn("Photo")}
                                    )
                                else:
                                    st.write("スタッツデータがまだありません。")
                            except Exception as e:
                                st.error(f"ボックススコアの取得に失敗しました: {e}")
                            
    except Exception as e:
        st.error(f"試合情報の取得に失敗しました: {e}")

with tab2:
    st.header("順位・個人成績トップページ")
    
    option = st.radio(
        "表示するデータを選択してください",
        ["チーム順位 (Standings)", "個人成績 (League Leaders)"],
        horizontal=True
    )
    
    if option == "チーム順位 (Standings)":
        st.subheader("チーム順位")
        try:
            df = get_standings()
            
            conf = st.selectbox("カンファレンス", ["All", "East", "West"])
            
            if conf != "All":
                df = df[df['Conference'] == conf].copy()
            else:
                df = df.copy()
            
            if 'strCurrentStreak' in df.columns:
                streak_col = 'strCurrentStreak'
            elif 'Streak' in df.columns:
                streak_col = 'Streak'
            else:
                streak_col = None
            
            # Add Logo URL Column
            df['Logo'] = df['TeamID'].apply(get_logo_url)
            
            # Rename PlayoffRank to Conf Rank
            df = df.rename(columns={'PlayoffRank': 'Conf Rank'})
                
            cols_to_show = ['Conf Rank', 'Logo', 'TeamName', 'Conference', 'Record', 'WINS', 'LOSSES', 'WinPCT', 'HOME', 'ROAD', 'L10']
            if streak_col:
                cols_to_show.append(streak_col)
                
            df_display = df[cols_to_show].copy()
            
            if conf != "All":
                df_display['Conf Rank'] = pd.to_numeric(df_display['Conf Rank'])
                df_display = df_display.sort_values('Conf Rank')
                df_display.reset_index(drop=True, inplace=True)
                
                def highlight_playoff_lines(row):
                    rank = row['Conf Rank']
                    styles = [''] * len(row)
                    if pd.notna(rank):
                        if rank == 6:
                            styles = ['border-bottom: 3px solid #1E88E5 !important;'] * len(row)
                        elif rank == 10:
                            styles = ['border-bottom: 3px solid #F4511E !important;'] * len(row)
                    return styles
                
                styled_df = df_display.style.apply(highlight_playoff_lines, axis=1).hide(axis="index")
                
                st.dataframe(
                    styled_df, 
                    height=600,
                    column_config={
                        "Logo": st.column_config.ImageColumn(
                            "Team", help="Team Logo"
                        ),
                        "Conf Rank": st.column_config.NumberColumn(
                            "Rank", width="small"
                        )
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.dataframe(
                    df_display, 
                    height=600,
                    column_config={
                        "Logo": st.column_config.ImageColumn(
                            "Team", help="Team Logo"
                        ),
                        "Conf Rank": st.column_config.NumberColumn(
                            "Rank", width="small"
                        )
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
            st.caption("※青線(=6位)より上がプレーオフ直行圏内、オレンジ線(=10位)より上がプレイイン・トーナメント圏内です。")
            
        except Exception as e:
            st.error(f"データの取得に失敗しました: {e}")
            
    elif option == "個人成績 (League Leaders)":
        st.subheader("個人成績")
        
        stat_mode = st.radio("集計方式", ["PerGame (平均)", "Totals (合計)"], horizontal=True)
        per_mode_param = "PerGame" if "PerGame" in stat_mode else "Totals"
        
        try:
            df = get_leaders(per_mode_param)
            
            stat_col = st.selectbox("スタッツカテゴリ", ["PTS", "REB", "AST", "STL", "BLK", "FG_PCT", "FG3_PCT", "FT_PCT"])
            
            # Additional logic for 3P% - ensure they take at least 1 attempt per game based on season totals
            # LeagueLeaders returns FG3A which is total restricted by per_mode
            if stat_col == "FG3_PCT":
                if per_mode_param == "Totals":
                    # If totals, check if FG3A / GP >= 1.0
                    df = df[(df['FG3A'] / df['GP']) >= 1.0].copy()
                else:
                    # If PerGame, FG3A is already the per game average
                    df = df[df['FG3A'] >= 1.0].copy()
                    
            # Add Logo URL Column to Leaders
            df['Logo'] = df['TEAM_ID'].apply(get_logo_url)
            
            # Add Headshot URL Column
            df['Photo'] = df['PLAYER_ID'].apply(get_headshot_url)
            
            df_display = df.sort_values(by=stat_col, ascending=False).head(50)
            
            # Format percentage columns correctly if they exist
            cols_to_disp = ['RANK', 'Photo', 'Logo', 'PLAYER', 'TEAM', 'GP', 'MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'FG_PCT', 'FG3_PCT', 'FT_PCT']
            cols_to_disp = [c for c in cols_to_disp if c in df_display.columns]
            
            # Format floats to 1 decimal place, percentages to 1 decimal place with %
            format_dict = {
                'FG_PCT': '{:.1%}', 'FG3_PCT': '{:.1%}', 'FT_PCT': '{:.1%}'
            }
            float_cols = ['MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK']
            for float_col in float_cols:
                if float_col in cols_to_disp:
                    format_dict[float_col] = '{:.1f}'
            
            styled_disp = df_display[cols_to_disp].style.format(format_dict, na_rep="").hide(axis="index")
            
            st.dataframe(
                styled_disp, 
                column_config={
                    "Logo": st.column_config.ImageColumn("Team", help="Team Logo"),
                    "Photo": st.column_config.ImageColumn("Photo", help="Player Photo")
                },
                use_container_width=True,
                hide_index=True
            )
            
            if stat_col == "FG3_PCT":
                st.caption("※3ポイント成功率は、1試合平均1本以上（試投）の選手のみを対象としています。")
                
        except Exception as e:
            st.error(f"データの取得に失敗しました: {e}")

# --- 前後1日分の事前キャッシュ（プリフェッチ） ---
# ページ最下部で実行することで、現在のUI描画を妨げずにバックグラウンドに近い形で処理されます。
# boxscore が CDN になり高速化・DDOS懸念が消滅したため安全に実行可能です。
def prefetch_adjacent_days():
    if 'current_date' not in st.session_state:
        return
    current_date = st.session_state.current_date
    for offset in [-1, 1]:
        target_date = current_date + timedelta(days=offset)
        api_date = date_to_api_format(target_date)
        try:
            # Scoreboard のみが遅延対象（0.6s Sleep x 2日分 = 計1.2秒）
            games_df, _ = get_scoreboard(api_date)
            
            # ボックススコアは CDN でミリ秒単位で終了するためスリープ対象外
            if not games_df.empty:
                for _, g in games_df.iterrows():
                    # 終了済みの試合のみボックススコアを取得
                    if g.get('gameStatus') == 3:
                        get_boxscore(g['gameId'])
        except Exception:
            pass # プリフェッチ失敗時は無視して進行

# 同期実行（約1.5秒程度で完了するためローディング体験を損ないません）
prefetch_adjacent_days()
