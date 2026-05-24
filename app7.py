import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import os
import time
from google import genai
from google.genai import types

st.set_page_config(page_title="מערכת AI לניהול סיכוני השקעות", page_icon="🛡️", layout="wide")

CSV_FILE = "portfolio.csv"

def save_portfolio_to_file():
    if st.session_state.portfolio:
        df = pd.DataFrame(st.session_state.portfolio)
        df.to_csv(CSV_FILE, index=False)
    else:
        if os.path.exists(CSV_FILE): os.remove(CSV_FILE)

def load_portfolio_from_file():
    if os.path.exists(CSV_FILE) and not st.session_state.portfolio:
        try:
            df = pd.read_csv(CSV_FILE)
            st.session_state.portfolio = df.to_dict(orient="records")
        except: st.session_state.portfolio = []

if "page" not in st.session_state: st.session_state.page = "setup"
if "portfolio" not in st.session_state: st.session_state.portfolio = []

load_portfolio_from_file()

st.sidebar.header("⚙️ הגדרות מערכת וסיכון")
api_key = st.sidebar.text_input("הזן מפתח API של Gemini:", type="password")
risk_profile = st.sidebar.selectbox("פרופיל סיכון מועדף", ["Conservative", "Moderate", "Aggressive"])
additional_capital = st.sidebar.number_input("הון חדש פנוי להשקעה (\$)", min_value=0, value=3000)

st.sidebar.markdown("---")
st.sidebar.header("📋 הגדרות סגנון הדוח")
report_type = st.sidebar.radio("סוג דוח מבוקש:", ["דוח מקוצר (תמציתי)", "דוח מלא ומורחב"])
report_lang = st.sidebar.radio("שפת הדוח מה-AI:", ["עברית (Hebrew)", "אנגלית (English)"])

@st.cache_data(ttl=900)
def fetch_stock_advanced_engine(ticker_str):
    try:
        stock = yf.Ticker(ticker_str)
        hist = stock.history(period="200d")
        if hist.empty: return None
        
        current_price = float(hist['Close'].iloc[-1])
        ma200 = float(hist['Close'].mean())
        trend = "📈 מגמה חיובית" if current_price > ma200 else "📉 מגמה שלילית"
        
        info = stock.info
        target_mean = info.get('targetMeanPrice', 'N/A')
        recommendation = info.get('recommendationKey', 'N/A')
        high_52w = info.get('fiftyTwoWeekHigh', current_price)
        
        pct_from_high = ((high_52w - current_price) / high_52w) * 100
        
        news_list = []
        raw_news = stock.news
        if raw_news:
            for item in raw_news[:4]:
                content = item.get("content", item)
                title = content.get("title", "No Title")
                news_list.append(title)
        
        # שומרים את הכותרת הראשונה בלבד כגרסה קלה למניעת חריגת 429 בהשוואות
        light_news = news_list[0] if news_list else "No news"
        news_summary = " | ".join(news_list) if news_list else "No recent news found."
        
        return {
            "price": current_price, "sector": info.get('sector', 'Unknown Sector'),
            "beta": info.get('beta', 1.0), "pe": info.get('trailingPE', 'N/A'),
            "market_cap": info.get('marketCap', 0), "trend": trend,
            "target_price": target_mean, "analyst_rating": recommendation, "news": news_summary,
            "light_news": light_news, "high_52w": high_52w, "pct_from_high": pct_from_high
        }
    except: return None
if st.session_state.page == "setup":
    st.title("💰 מסך פתיחה: הגדרת התיק הקיים")
    if os.path.exists(CSV_FILE): st.info("📂 נתוני התיק שלך נטענו אוטומטית מהשמירה האחרונה במחשב.")
        
    portfolio_cash = st.number_input("יתרת מזומן נוכחית בתיק (\$):", min_value=0, value=2000)
    st.subheader("➕ הוספת מניה לתיק")
    col_t, col_s = st.columns(2)
    new_ticker = col_t.text_input("סימול מניה (למשל AAPL):", "").upper().strip()
    new_shares = col_s.number_input("כמות מניות:", min_value=1, value=1)
    
    if st.button("הוסף מניה לתיק"):
        if new_ticker:
            with st.spinner(f"בודק את הסימול {new_ticker}..."):
                data = fetch_stock_advanced_engine(new_ticker)
            if data:
                exists = False
                for item in st.session_state.portfolio:
                    if item['ticker'] == new_ticker:
                        item['shares'] += new_shares
                        exists = True
                        break
                if not exists:
                    st.session_state.portfolio.append({
                        "ticker": new_ticker, "shares": new_shares, "price": data["price"], 
                        "sector": data["sector"], "beta": data["beta"], "pe": data["pe"],
                        "market_cap": data["market_cap"], "trend": data["trend"]
                    })
                save_portfolio_to_file()
                st.success(f"✔️ המניה {new_ticker} נוספה ונשמרה בתיק!")
                st.rerun()
            else: st.error("❌ סימול לא נמצא ב-Yahoo Finance.")

    total_portfolio_value = portfolio_cash
    rows = []
    for item in st.session_state.portfolio:
        current_value = item["shares"] * item["price"]
        total_portfolio_value += current_value
        rows.append({"נכס": item["ticker"], "כמות": item["shares"], "מחיר נוכחי": f"\${item['price']:.2f}", "שווי פוזיציה": current_value, "סקטור": item["sector"], "בטא": item["beta"]})
        
    if rows or portfolio_cash > 0:
        st.write("---")
        st.subheader("📊 סיכום התיק הנוכחי")
        chart_rows = rows.copy()
        chart_rows.append({"נכס": "Cash (מזומן)", "שווי פוזיציה": portfolio_cash, "סקטור": "Cash"})
        df_chart = pd.DataFrame(chart_rows)
        c1, c2 = st.columns(2)
        c1.metric("שווי תיק כולל (מניות + מזומן)", f"\${total_portfolio_value:,.2f}")
        total_stock_val = sum(r["שווי פוזיציה"] for r in rows)
        weighted_beta = 1.0
        if total_stock_val > 0:
            weighted_beta = sum(r["בטא"] * (r["שווי פוזיציה"] / total_stock_val) for r in rows)
        c2.metric("מדד תנודתיות התיק (Beta משוקללת)", f"{weighted_beta:.2f}")
        fig = px.pie(df_chart, values="שווי פוזיציה", names="נכס", title="פילוח נכסים בתיק ההשקעות", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
        
        if rows:
            st.dataframe(pd.DataFrame(rows)[["נכס", "כמות", "מחיר נוכחי", "שווי פוזיציה", "סקטור"]], use_container_width=True)
            if st.button("🗑️ איפוס ומחיקת התיק לצמיתות"):
                st.session_state.portfolio = []
                save_portfolio_to_file()
                st.rerun()
        st.write("---")
        if st.button("➡️ המשך למסך ניתוח והשקעות החדשות", type="primary"):
            st.session_state.total_portfolio_value = total_portfolio_value
            st.session_state.portfolio_cash = portfolio_cash
            st.session_state.page = "analysis"
            st.rerun()
elif st.session_state.page == "analysis":
    st.title("🛡️ מסך ניתוח: בחינת פוטנציאל השקעה")
    if st.button("⬅️ חזור לעריכת התיק"):
        st.session_state.page = "setup"
        st.rerun()
    st.write(f"💼 **שווי התיק המחושב שלך:** \${st.session_state.total_portfolio_value:,.2f} | 💵 **הון חדש להשקעה:** \${additional_capital:,.2f}")
    mode = st.radio("בחר את אופן בחינת ההשקעה החדשה:", ["🧐 בחינת מניה בודדת כפוטנציאל השקעה", "⚔️ השוואה בין מספר מניות כפוטנציאל השקעה"])
    
    portfolio_desc = ""
    for k in st.session_state.portfolio:
        portfolio_desc += f"- מניית {k['ticker']}: מחזיק \${k['shares']*k['price']:.2f} (סקטור: {k['sector']}, בטא: {k['beta']})\n"
    portfolio_desc += f"- מזומן פנוי בתיק: \${st.session_state.portfolio_cash:.2f}\n"

    lang_instruction = "Respond ONLY in Hebrew." if report_lang == "עברית (Hebrew)" else "Respond ONLY in English. Do not use Hebrew letters at all."
    format_instruction = "Provide a SHORT, ultra-concise report. Ensure both Analysis #1 and Analysis #2 are strictly answered in 2-3 sentences each max." if report_type == "דוח מקוצר (תמציתי)" else "Provide a FULL, comprehensive investment report. Deeply expand both Analysis #1 and Analysis #2 with mathematical justification, sector correlation, news details, and advanced entry strategies."

    if mode == "🧐 בחינת מניה בודדת כפוטנציאל השקעה":
        target_ticker = st.text_input("הזן סימול מניה לבחינה (למשל NVDA):", "NVDA").upper().strip()
        if st.button("נתח מניה והפק המלצה"):
            if not api_key: st.warning("אנא הזן מפתח API ב-Sidebar")
            elif target_ticker:
                with st.spinner("מנוע ה-AI מריץ ניתוח תיק וניתוח מניה מפוצל..."):
                    data = fetch_stock_advanced_engine(target_ticker)
                if data:
                    existing_val = sum(item["shares"] * item["price"] for item in st.session_state.portfolio if item["ticker"] == target_ticker)
                    current_concen = (existing_val / st.session_state.total_portfolio_value) * 100
                    potential_new_val = existing_val + additional_capital
                    potential_concen = (potential_new_val / st.session_state.total_portfolio_value) * 100
                    
                    st.subheader("📊 טבלת ריכוז נתוני שינוי חשיפה (לפני מול אחרי)")
                    overview_data = [
                        {"מדד": "שווי פוזיציה במניה", "מצב נוכחי (לפני)": f"\${existing_val:,.2f}", "מצב עתידי (אחרי)": f"\${potential_new_val:,.2f}"},
                        {"מדד": "אחוז ריכוזיות בתיק", "מצב נוכחי (לפני)": f"{current_concen:.1f}%", "מצב עתידי (אחרי)": f"{potential_concen:.1f}%"}
                    ]
                    st.dataframe(pd.DataFrame(overview_data), use_container_width=True)
                    
                    st.subheader("📰 נתוני שוק ותמחור טקטי")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("קונזנזוס אנליסטים", str(data['analyst_rating']).upper())
                    col2.metric("מחיר יעד ממוצע", f"${data['target_price']}")
                    col3.metric("מרחק מהשיא השנתי", f"{data['pct_from_high']:.1f}%")
                    col4.metric("מגמה (200 יום)", data['trend'])
                    
                    with st.expander("👀 צפה בכותרות החדשות האחרונות שנשלחו ל-AI"):
                        st.write(data['news'])
                    
                    user_context = f"[מצב תיק קיים]\nשווי כולל: \${st.session_state.total_portfolio_value:.2f}\nפירוט נכסים:\n{portfolio_desc}\n\n[העסקה המבוקשת]\nהמשתמש רוצה להשקיע סכום חדש של \${additional_capital} במניית {target_ticker}.\nנתוני שוק: סקטור {data['sector']}, בטא {data['beta']:.2f}, מכפיל {data['pe']}, מגמה {data['trend']}.\nמרחק המניה כרגע משיא 52 שבועות: {data['pct_from_high']:.1f}% מתחת לשיא.\nהמלצות אנליסטים: קונזנזוס {data['analyst_rating']}, מחיר יעד ${data['target_price']}.\nחדשות אחרונות: {data['news']}.\nחשיפה נוכחית: {current_concen:.1f}%, חשיפה פוטנציאלית סופית: {potential_concen:.1f}%."
                    system_instruction = f"אתה אנליסט פיננסי ומנהל סיכונים בכיר. המשתמש פועל תחת פרופיל סיכון {risk_profile}. בצע בדיקה מפוצלת: ### 📂 ניתוח 1: התאמה לתיק ורמת סיכון (אכוף חוקי ריכוזיות ובטא). ### 📈 ניתוח 2: הערכת המניה עצמה ותזמון טקטי (קבע אם לקנות כעת, לחכות למחיר זול יותר לשיפור פוזיציה, או לא לקנות בכלל על בסיס מרחק מהשיא {data['pct_from_high']:.1f}%, אנליסטים וחדשות). {lang_instruction} {format_instruction}"
                    
                    # לולאת הגנה חסינת 429
                    response_text = None
                    for attempt in range(3):
                        try:
                            client = genai.Client(api_key=api_key)
                            response = client.models.generate_content(model='gemini-2.5-flash', contents=user_context, config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.1))
                            response_text = response.text
                            break
                        except Exception as e:
                            if "429" in str(e) and attempt < 2:
                                with st.spinner(f"שרת גוגל עמוס, מבצע ניסיון חוזר אוטומטי בעוד 4 שניות... (ניסיון {attempt+1}/3)"):
                                    time.sleep(4)
                            else:
                                st.error(f"שגיאה קריטית בחיבור ל-AI: {str(e)}")
                                break
                    if response_text:
                        st.write("---")
                        st.subheader(f"🤖 דוח מפוצל מה-AI ({report_type} | {report_lang})")
                        st.markdown(response_text)
                else: st.error("הסימול לא נמצא בשוק.")
                    
    else:
        st.subheader("⚔️ השוואה בין מספר נכסים פוטנציאליים")
        tickers_list_raw = st.text_input("הזן סימולים להשוואה (מופרדים בפסיק, למשל: NVDA, AMD, TSLA):", "NVDA, AMD")
        if st.button("בצע השוואה והפק המלצה"):
            if not api_key: st.warning("אנא הזן מפתח API ב-Sidebar")
            else:
                tickers = [t.strip().upper() for t in tickers_list_raw.split(",") if t.strip()]
                comparison_data = []
                with st.spinner("שולף נתוני אמת מורחבים עבור כל המניות להשוואה..."):
                    for t in tickers:
                        d = fetch_stock_advanced_engine(t)
                        if d:
                            existing_val = sum(item["shares"] * item["price"] for item in st.session_state.portfolio if item["ticker"] == t)
                            current_concen = (existing_val / st.session_state.total_portfolio_value) * 100
                            potential_concen = ((existing_val + additional_capital) / st.session_state.total_portfolio_value) * 100
                            comparison_data.append({
                                "מניה": t, "מחיר נוכחי": f"\${d['price']:.2f}", "סקטור": d["sector"], "בטא": d["beta"], 
                                "דירוג אנליסטים": str(d['analyst_rating']).upper(), "מחיר יעד": f"${d['target_price']}",
                                "מרחק משיא": f"{d['pct_from_high']:.1f}%", "חשיפה לפני": f"{current_concen:.1f}%", "חשיפה אחרי": f"{potential_concen:.1f}%",
                                "light_news": d['light_news']
                            })
                if comparison_data:
                    st.subheader("📊 טבלת ריכוז והשוואה מורחבת (לפני מול אחרי)")
                    df_comp = pd.DataFrame(comparison_data)
                    st.dataframe(df_comp[["מניה", "מחיר נוכחי", "סקטור", "בטא", "דירוג אנליסטים", "מחיר יעד", "מרחק משיא", "חשיפה לפני", "חשיפה אחרי"]], use_container_width=True)
                    
                    comp_desc = ""
                    for c in comparison_data:
                        comp_desc += f"- מניית {c['מניה']}: סקטור {c['סקטור']}, בטא {c['בטא']:.2f}, אנליסטים: {c['דירוג אנליסטים']}, מרחק מהשיא {c['מרחק משיא']}. חדשות: {c['light_news']}.\n"
                    user_context = f"[מצב תיק קיים]\nשווי כולל: \${st.session_state.total_portfolio_value:.2f}\nפירוט נכסים:\n{portfolio_desc}\n\n[דילמת ההשקעה]\nהמשתמש מתלבט איפה להשקיע \${additional_capital} מבין האפשרויות:\n{comp_desc}"
                    system_instruction = f"אתה מנהל סיכונים בכיר. השווה בין החלופות עבור פרופיל {risk_profile}. שקלל את חוקי הריכוזיות, רמות התנודתיות, והמרחק מהשיא השנתי של כל מניה. פורמט פלט: ענה בעברית. ספק סיכום והמלצה ברורה בשורה התחתונה."
                    
                    # לולאת הגנה חסינת 429 להשוואה
                    response_text = None
                    for attempt in range(3):
                        try:
                            client = genai.Client(api_key=api_key)
                            response = client.models.generate_content(model='gemini-2.5-flash', contents=user_context, config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.1))
                            response_text = response.text
                            break
                        except Exception as e:
                            if "429" in str(e) and attempt < 2:
                                with st.spinner(f"עומס בשרת גוגל, מבצע ניסיון חוזר אוטומטי בעוד 5 שניות... (ניסיון {attempt+1}/3)"):
                                    time.sleep(5)
                            else:
                                st.error(f"שגיאה קריטית בהשוואת ה-AI: {str(e)}")
                                break
                    if response_text:
                        st.write("---")
                        st.subheader(f"🤖 {report_type} מה-AI ({report_lang})")
                        st.markdown(response_text)
                else: st.error("לא נמצאו נתוני שוק עבור הסימולים שהוזנו.")
