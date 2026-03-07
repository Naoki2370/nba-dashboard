import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
from nba_api.stats.endpoints import scoreboardv2, boxscoretraditionalv3, leaguestandings, leagueleaders
from nba_api.stats.static import teams

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

# Caching API Calls
@st.cache_data(ttl=600)
def get_scoreboard(date_str):
    board = scoreboardv2.ScoreboardV2(game_date=date_str)
    return board.game_header.get_data_frame(), board.line_score.get_data_frame()

@st.cache_data(ttl=600)
def get_boxscore(game_id):
    boxscore = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
    return boxscore.player_stats.get_data_frame()

@st.cache_data(ttl=600)
def get_standings():
    standings = leaguestandings.LeagueStandings()
    return standings.standings.get_data_frame()

@st.cache_data(ttl=600)
def get_leaders(per_mode):
    leaders = leagueleaders.LeagueLeaders(per_mode48=per_mode)
    return leaders.league_leaders.get_data_frame()

# NBA Teams List
nba_teams = [team['full_name'] for team in teams.get_teams()]
nba_teams.sort()

with tab1:
    st.header("試合情報一覧")
    
    if 'current_date' not in st.session_state:
        st.session_state.current_date = get_jst_today()
        
    col1, col2, col3, col4 = st.columns([1, 4, 1, 1])
    
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

    favorite_teams = st.multiselect("お気に入りチームを選択（上位に表示）", options=nba_teams)
    
    # 日本時間(JST)のその日に行われる試合は、米国時間では前日の日付で管理されているため、-1日してAPIにリクエストします
    api_date_query = date_to_api_format(st.session_state.current_date - timedelta(days=1))
    display_date = st.session_state.current_date.strftime("%Y/%m/%d")
    
    st.subheader(f"{display_date} (日本時間) の試合")
    
    try:
        games_df, linescores = get_scoreboard(api_date_query)
        
        if games_df.empty:
            st.info("この日の試合はありません。")
        else:
            games_list = []
            for index, game in games_df.iterrows():
                game_id = game['GAME_ID']
                home_team_id = game['HOME_TEAM_ID']
                visitor_team_id = game['VISITOR_TEAM_ID']
                
                home_team_data = linescores[linescores['TEAM_ID'] == home_team_id]
                visitor_team_data = linescores[linescores['TEAM_ID'] == visitor_team_id]
                
                h_city = home_team_data['TEAM_CITY_NAME'].values[0] if not home_team_data.empty else ""
                h_name = home_team_data['TEAM_NAME'].values[0] if not home_team_data.empty else ""
                home_full_name = f"{h_city} {h_name}".strip()
                home_team_abbr = home_team_data['TEAM_ABBREVIATION'].values[0] if not home_team_data.empty else "Home"
                
                v_city = visitor_team_data['TEAM_CITY_NAME'].values[0] if not visitor_team_data.empty else ""
                v_name = visitor_team_data['TEAM_NAME'].values[0] if not visitor_team_data.empty else ""
                visitor_full_name = f"{v_city} {v_name}".strip()
                visitor_team_abbr = visitor_team_data['TEAM_ABBREVIATION'].values[0] if not visitor_team_data.empty else "Visitor"
                
                home_pts = home_team_data['PTS'].values[0] if not home_team_data.empty else "-"
                visitor_pts = visitor_team_data['PTS'].values[0] if not visitor_team_data.empty else "-"
                
                is_favorite = False
                if home_full_name in favorite_teams or visitor_full_name in favorite_teams:
                    is_favorite = True
                    
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
                    'is_favorite': is_favorite
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
                    with c4:
                        st.markdown(f"<h3 style='text-align: left; margin-top: 10px;'>{g['home_full']}</h3>", unsafe_allow_html=True)
                    with c5:
                        st.image(get_logo_url(g['home_id']), width=50)
                    
                    with st.expander("ボックススコアを見る"):
                        try:
                            player_stats = get_boxscore(g['game_id'])
                            
                            if not player_stats.empty:
                                def format_boxscore(df, team_id):
                                    tdf = df[df['teamId'] == team_id].copy()
                                    tdf['PLAYER_NAME'] = tdf['firstName'] + " " + tdf['familyName']
                                    
                                    # Identify starters and extract position
                                    tdf['is_starter'] = tdf['position'].apply(lambda x: pd.notna(x) and str(x).strip() != "")
                                    tdf['POS'] = tdf['position'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() != "" else "")
                                    tdf['NO.'] = tdf['jerseyNum'].apply(lambda x: str(x) if pd.notna(x) else "")
                                    
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
                                    cols = ['NO.', 'PLAYER_NAME', 'POS', 'MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 
                                            'FGM', 'FGA', 'FG%', '3PM', '3PA', '3P%', 'FTM', 'FTA', 'FT%', '+/-', 'is_starter']
                                    
                                    # Only keep columns that exist
                                    cols = [c for c in cols if c in tdf.columns]
                                    tdf = tdf[cols]
                                    
                                    # Styling function to bold starters and add bottom border to the last starter
                                    def highlight_starters(row):
                                        idx = row.name
                                        is_starter = tdf.loc[idx, 'is_starter']
                                        next_is_starter = False
                                        
                                        # Convert index to integer-based lookup for next row
                                        try:
                                            row_loc = tdf.index.get_loc(idx)
                                            if row_loc < len(tdf) - 1:
                                                next_is_starter = tdf.iloc[row_loc + 1]['is_starter']
                                        except:
                                            pass
                                            
                                        styles = [''] * len(row)
                                        if is_starter:
                                            styles = ['font-weight: bold'] * len(row)
                                            # If this is the last starter, add a border
                                            if not next_is_starter:
                                                styles = [s + '; border-bottom: 2px solid #888888 !important;' for s in styles]
                                        return styles
                                    
                                    # Drop the helper col before display
                                    styled_df = tdf.drop(columns=['is_starter']).style.apply(highlight_starters, axis=1).hide(axis="index")
                                    # Format percentages and floats
                                    format_dict = {
                                        'FG%': '{:.1%}', '3P%': '{:.1%}', 'FT%': '{:.1%}', '+/-': '{:+.0f}'
                                    }
                                    styled_df = styled_df.format(formatter={k: v for k, v in format_dict.items() if k in tdf.columns}, na_rep="")
                                    
                                    return styled_df

                                st.write(f"**{g['visitor_full']} Stats**")
                                st.dataframe(format_boxscore(player_stats, g['visitor_id']), use_container_width=True, hide_index=True)
                                
                                st.write(f"**{g['home_full']} Stats**")
                                st.dataframe(format_boxscore(player_stats, g['home_id']), use_container_width=True, hide_index=True)
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
            
            df_display = df.sort_values(by=stat_col, ascending=False).head(50)
            
            # Format percentage columns correctly if they exist
            cols_to_disp = ['RANK', 'Logo', 'PLAYER', 'TEAM', 'GP', 'MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'FG_PCT', 'FG3_PCT', 'FT_PCT']
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
                    "Logo": st.column_config.ImageColumn("Team", help="Team Logo")
                },
                use_container_width=True,
                hide_index=True
            )
            
            if stat_col == "FG3_PCT":
                st.caption("※3ポイント成功率は、1試合平均1本以上（試投）の選手のみを対象としています。")
                
        except Exception as e:
            st.error(f"データの取得に失敗しました: {e}")
