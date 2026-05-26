import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import os
import time
from google import genai
from google.genai import types

# הגדרת תצורת הדף - תמיכה ברוחב מלא וכותרת מערכת
st.set_page_config(page_title="מערכת AI לניהול סיכוני השקעות", page_icon="📊", layout="wide")

CSV_FILE = "portfolio.csv"

def save_portfolio_to_file():
    """שמירת מצב התיק הנוכחי לקובץ CSV מקומי"""
    if st.session_state.portfolio:
        df = pd.DataFrame(st.session_state.portfolio)
        df.to_csv(CSV_FILE, index=False)
    else:
        if os.path.exists(CSV_FILE): 
            os.remove(CSV_FILE)

def load_portfolio_from_file():
    """טעינת התיק השמור מהמחשב במידה וקיים"""
    if os.path.exists(CSV_FILE) and not st.session_state.portfolio:
        try:
            df = pd.read_csv(CSV_FILE)
            st.session_state.portfolio = df.to_dict(orient="records")
        except: 
            st.session_state.portfolio = []

# אתחול משתני State גלובליים למערכת
if "page" not in st.session_state: 
    st.session_state.page = "setup"
if "portfolio" not in st.session_state: 
    st.session_state.portfolio = []

# טעינה ראשונית של התיק
load_portfolio_from_file()
# --- תפריט צד: הגדרות מערכת וסיכון ---
st.sidebar.header("⚙️ הגדרות מערכת וסיכון")

# ניהול מפתח ה-API של Gemini
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ מפתח API נטען אוטומטית") 
else:
    api_key = st.sidebar.text_input("הזן מפתח API של Gemini:", type="password")

# פרופיל סיכון והון להשקעה
risk_profile = st.sidebar.selectbox("פרופיל סיכון מועדף:", ["Conservative", "Moderate", "Aggressive"])
additional_capital = st.sidebar.number_input("הון חדש פנוי להשקעה ($):", min_value=0, value=3000)

st.sidebar.markdown("---")
st.sidebar.header("🌐 הגדרות שפה")
report_lang = st.sidebar.radio("שפת דוח ה-AI:", ["עברית (Hebrew)", "אנגלית (English)"])

@st.cache_data(ttl=900)
def fetch_stock_advanced_engine(ticker_str):
    """שליפת נתוני שוק בזמן אמת, חדשות וחישוב מדדי סיכון היסטוריים"""
    try:
        stock = yf.Ticker(ticker_str)
        hist = stock.history(period="200d")
        if hist.empty: 
            return None
        
        # חישוב מחיר ומגמה טכנית (ממוצע נע 200)
        current_price = float(hist['Close'].iloc[-1])
        ma200 = float(hist['Close'].mean())
        trend = "מגמה חיובית 📈" if current_price > ma200 else "מגמה שלילית 📉"
        
        # חישוב מדדי סיכון מתקדמים (שיפור)
        daily_returns = hist['Close'].pct_change().dropna()
        historical_volatility = float(daily_returns.std() * np.sqrt(252)) * 100  # סטיית תקן שנתית באחוזים
        six_month_return = float((current_price - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100

        # שליפת נתוני פונדמנטלס ומטרות אנליסטים
        info = getattr(stock, 'info', {})
        target_mean = info.get('targetMeanPrice', 'N/A')
        recommendation = info.get('recommendationKey', 'N/A')
        high_52w = info.get('fiftyTwoWeekHigh', current_price)
        sector = info.get('sector', 'Unknown Sector')
        pe = info.get('trailingPE', 'N/A')
        market_cap = info.get('marketCap', 0)
        beta = info.get('beta', 1.0)
        
        # מרחק מהשיא השנתי
        pct_from_high = ((high_52w - current_price) / high_52w) * 100 if high_52w else 0.0
        
        # שליפת חדשות אחרונות
        news_list = []
        try:
            raw_news = stock.news
            if raw_news:
                for item in raw_news[:4]:
                    content = item.get("content", item)
                    title = content.get("title", "No Title")
                    news_list.append(title)
        except: 
            pass
        
        light_news = news_list if news_list else ["No news available"]
        news_summary = " | ".join(news_list) if news_list else "No recent news found."
        
        return {
            "price": current_price, "sector": sector, "beta": beta, "pe": pe,
            "market_cap": market_cap, "trend": trend, "target_price": target_mean, 
            "analyst_rating": recommendation, "news": news_summary, "light_news": light_news, 
            "high_52w": high_52w, "pct_from_high": pct_from_high,
            "volatility": historical_volatility, "six_month_return": six_month_return
        }
    except: 
        return None
# --- מסך הגדרת התיק הקיים ---
if st.session_state.page == "setup":
    st.title("💰 מסך פתיחה: הגדרת התיק הקיים") 
    
    if os.path.exists(CSV_FILE): 
        st.info("📂 נתוני התיק שלך נטענו אוטומטית מהשמירה האחרונה במחשב.")
    
    portfolio_cash = st.number_input("יתרת מזומן נוכחית בתיק ($):", min_value=0, value=2000)
    
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
                    st.success(f"המניה {new_ticker} נוספה בצלחה לתיק ונשמרה!")
                    st.rerun()
                else:
                    st.error("❌ הסימול לא נמצא ב-Yahoo Finance או שיש בעיית תקשורת זמנית.")

    # חישובים וסיכום התיק הנוכחי
    total_portfolio_value = portfolio_cash
    rows = []
    for item in st.session_state.portfolio:
        current_value = item["shares"] * item["price"]
        total_portfolio_value += current_value
        rows.append({
            "נכס": item["ticker"], "כמות": item["shares"], 
            "מחיר נוכחי": f"${item['price']:.2f}", "שווי פוזיציה ($)": current_value, 
            "סקטור": item["sector"], "בטא": item["beta"]
        })
    
    if rows or portfolio_cash > 0:
        st.write("---")
        st.subheader("📊 סיכום ומדדי התיק הנוכחי")
        
        # הצגת מדדים מרכזיים עם תיקון כיווניות טקסט
        c1, c2 = st.columns(2)
        c1.metric(label="שווי תיק כולל (מזומן + מניות)", value=f"${total_portfolio_value:,.2f}")
        
        total_stock_val = sum(r["שווי פוזיציה ($)"] for r in rows)
        weighted_beta = 1.0
        if total_stock_val > 0:
            weighted_beta = sum(r["בטא"] * (r["שווי פוזיציה ($)"] / total_stock_val) for r in rows)
        c2.metric(label="מדד תנודתיות תיק משוקלל (Beta)", value=f"{weighted_beta:.2f}")
        
        # טבלת פירוט הנכסים
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            
        # מעבר למסך הבא או איפוס
        col_b1, col_b2 = st.columns(2)
        if col_b1.button("🗑️ איפוס ומחיקת התיק לצמיתות", type="secondary"):
            st.session_state.portfolio = []
            save_portfolio_to_file()
            st.rerun()
            
        if col_b2.button("🚀 המשך למסך ניתוח והשקעות חדשות", type="primary"):
            st.session_state.total_portfolio_value = total_portfolio_value
            st.session_state.portfolio_cash = portfolio_cash
            st.session_state.page = "analysis"
            st.rerun()
elif st.session_state.page == "analysis":
    st.title("🔍 מסך ניתוח: בחינת פוטנציאל השקעה") 
    
    if st.button("⬅️ חזור לעריכת התיק"):
        st.session_state.page = "setup"
        st.rerun()
        
    st.info(f"**שווי התיק המחושב שלך:** ${st.session_state.total_portfolio_value:,.2f} | **הון חדש פנוי להשקעה:** ${additional_capital:,.2f}")
    
    mode = st.radio("בחר את אופן בחינת ההשקעה החדשה:", [
        "בחינת מניה בודדת כפוטנציאל השקעה", 
        "השוואה בין מספר מניות כפוטנציאל השקעה"
    ])
    
    # בניית תיאור טקסטואלי של התיק עבור ה-AI
    portfolio_desc = ""
    current_chart_data = [{"נכס": "Cash", "שווי ($)": st.session_state.portfolio_cash}]
    
    for k in st.session_state.portfolio:
        val = k['shares'] * k['price']
        portfolio_desc += f"- מניית {k['ticker']}: מחזיק בשווי ${val:.2f} (סקטור: {k['sector']}, בטא: {k['beta']})\n"
        current_chart_data.append({"נכס": k['ticker'], "שווי ($)": val})
        
    portfolio_desc += f"- מזומן פנוי בתיק: ${st.session_state.portfolio_cash:.2f}\n"

    if mode == "בחינת מניה בודדת כפוטנציאל השקעה":
        target_ticker = st.text_input("הזן סימול מניה לבחינה (למשל NVDA):", "NVDA").upper().strip()
        
        if st.button("📊 נתח מניה והצג סימולציה", type="primary"):
            if not api_key:
                st.warning("⚠️ אנא הזן מפתח API בתפריט הצדדי")
            elif target_ticker:
                with st.spinner(f"שולף נתונים ומריץ סימולציה עבור {target_ticker}..."):
                    data = fetch_stock_advanced_engine(target_ticker)
                    if data:
                        existing_val = sum(item["shares"] * item["price"] for item in st.session_state.portfolio if item["ticker"] == target_ticker)
                        current_concen = (existing_val / st.session_state.total_portfolio_value) * 100 if st.session_state.total_portfolio_value > 0 else 0
                        
                        potential_new_val = existing_val + additional_capital
                        new_total_value = st.session_state.total_portfolio_value + additional_capital
                        potential_concen = (potential_new_val / new_total_value) * 100
                        
                        # --- שדרוג: סימולציית "מה אם" ויזואלית ---
                        st.subheader("📊 סימולציית פילוח נכסים: מצב נוכחי מול עתידי")
                        future_chart_data = []
                        found_future = False
                        
                        for item in current_chart_data:
                            if item["נכס"] == target_ticker:
                                future_chart_data.append({"נכס": item["נכס"], "שווי ($)": item["שווי ($)"] + additional_capital})
                                found_future = True
                            else:
                                future_chart_data.append(item.copy())
                        if not found_future:
                            future_chart_data.append({"נכס": target_ticker, "שווי ($)": additional_capital})
                            
                        col_fig1, col_fig2 = st.columns(2)
                        fig_curr = px.pie(pd.DataFrame(current_chart_data), values="שווי ($)", names="נכס", title="מבנה התיק הנוכחי", hole=0.4)
                        fig_fut = px.pie(pd.DataFrame(future_chart_data), values="שווי ($)", names="נכס", title=f"מבנה התיק לאחר רכישת {target_ticker}", hole=0.4)
                        col_fig1.plotly_chart(fig_curr, use_container_width=True)
                        col_fig2.plotly_chart(fig_fut, use_container_width=True)
                        
                        # טבלת שינוי חשיפה ריכוזית
                        st.subheader("📈 שינוי ריכוזיות וחשיפה בתיק")
                        overview_data = [
                            {"מדד": "שווי פוזיציה במניה ($)", "מצב נוכחי (לפני)": f"${existing_val:,.2f}", "מצב עתידי (אחרי)": f"${potential_new_val:,.2f}"},
                            {"מדד": "אחוז ריכוזיות מהתיק", "מצב נוכחי (לפני)": f"{current_concen:.1f}%", "מצב עתידי (אחרי)": f"{potential_concen:.1f}%"}
                        ]
                        st.dataframe(pd.DataFrame(overview_data), use_container_width=True)
                        
                        # נתוני שוק טקטיים ומדדי סיכון משודרגים
                        st.subheader("🎯 נתוני שוק ומדדי סיכון מתקדמים")
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("קונזנזוס אנליסטים", str(data['analyst_rating']).upper())
                        col2.metric("מחיר יעד ממוצע", f"${data['target_price']}")
                        col3.metric("תנודתיות היסטורית (סטיית תקן)", f"{data['volatility']:.1f}%")
                        col4.metric("תשואה חצי-שנתית", f"{data['six_month_return']:.1f}%")

                        st.session_state.last_context = {
                            "ticker": target_ticker, "data": data, 
                            "current_concen": current_concen, "potential_concen": potential_concen,
                            "portfolio_desc": portfolio_desc, "report_lang": report_lang, "risk_profile": risk_profile
                        }
                    else:
                        st.error("❌ לא ניתן היה לשלוף נתוני שוק עבור סימול זה.")
        # הצגת כפתורי הפקת דוח ה-AI במידה ויש נתונים שמורים ב-State
        if "last_context" in st.session_state and st.session_state.last_context["ticker"] == target_ticker:
            ctx = st.session_state.last_context
            lang_instruction = "Respond ONLY in Hebrew." if ctx["report_lang"] == "עברית (Hebrew)" else "Respond ONLY in English. Do not use Hebrew letters at all."
            
            # שדרוג: ניתוח סנטימנט חדשות מובנה באמצעות ה-AI
            st.write("---")
            st.subheader("📰 ניתוח סנטימנט חדשות מהיר (AI Sentiment)")
            if st.button("נתח סנטימנט חדשות"):
                with st.spinner("מנתח את כותרות החדשות האחרונות..."):
                    try:
                        client = genai.Client(api_key=api_key)
                        sentiment_prompt = f"Analyze the sentiment of the following headlines for {ctx['ticker']} and give a brief summary, rating (Positive/Negative/Neutral) and trend direction: {ctx['data']['news']}. {lang_instruction}"
                        sent_response = client.models.generate_content(model='gemini-2.5-flash', contents=sentiment_prompt)
                        st.info(sent_response.text)
                    except Exception as e:
                        st.error(f"שגיאה בניתוח הסנטימנט: {str(e)}")

            # כפתור להפקת דוח השקעות מלא ומורחב
            if st.button("✨ הפק דוח השקעות מורחב ומלא של ה-AI", type="primary"):
                with st.spinner("מנוע ה-AI מפיק דוח עומק מפורט (עשוי לקחת מספר שניות)..."):
                    user_context = f"""
                    [מצב תיק קיים] שווי כולל: ${st.session_state.total_portfolio_value:.2f}
                    פירוט נכסים:
                    {ctx['portfolio_desc']}
                    
                    [העסקה המבוקשת] המשתמש רוצה להשקיע סכום חדש של ${additional_capital:.2f} במניית {ctx['ticker']}.
                    נתוני שוק: סקטור {ctx['data']['sector']}, בטא {ctx['data']['beta']:.2f}, מכפיל {ctx['data']['pe']}, מגמה {ctx['data']['trend']}.
                    מרחק מהשיא: {ctx['data']['pct_from_high']:.1f}%, תנודתיות שנתית: {ctx['data']['volatility']:.1f}%.
                    קונזנזוס אנליסטים: {ctx['data']['analyst_rating']}, מחיר יעד ${ctx['data']['target_price']}.
                    חדשות: {ctx['data']['news']}.
                    חשיפה נוכחית: {ctx['current_concen']:.1f}%, חשיפה סופית פוטנציאלית: {ctx['potential_concen']:.1f}%.
                    """
                    
                    system_instruction_full = f"""
                    אתה אנליסט פיננסי ומנהל סיכונים בכיר. המשתמש פועל תחת פרופיל סיכון {ctx['risk_profile']}.
                    בצע בדיקה מפוצלת מורחבת ומעמיקה במיוחד:
                    ### ניתוח 1: התאמה לתיק ורמת סיכון (כלול חישובי ריכוזיות, בטא, ומתאם סקטוריאלי).
                    ### ניתוח 2: הערכת המניה עצמה ותזמון טקטי (ספק נימוק מורחב מבין האפשרויות: לקנות כעת, לחכות למחיר זול יותר, או לא לקנות בכלל).
                    שלב ניתוח מתקדם על סמך התנודתיות ההיסטורית שנמסרה ({ctx['data']['volatility']:.1f}%).
                    Provide a FULL, comprehensive investment report with mathematical justification. {lang_instruction}
                    """
                    
                    # מנגנון חוסן עם Retry אוטומטי למניעת שגיאות 429
                    response_text = None
                    for attempt in range(3):
                        try:
                            client = genai.Client(api_key=api_key)
                            response_full = client.models.generate_content(
                                model='gemini-2.5-flash', 
                                contents=user_context, 
                                config=types.GenerateContentConfig(system_instruction=system_instruction_full, temperature=0.2)
                            )
                            response_text = response_full.text
                            break
                        except Exception as e:
                            if "429" in str(e) and attempt < 2:
                                st.warning("עומס זמני בשרת, מנסה שוב בעוד 5 שניות...")
                                time.sleep(5)
                            else:
                                st.error(f"שגיאה בהפקת הדוח: {str(e)}")
                                break
                    
                    if response_text:
                        st.subheader("📑 דוח אנליטי מלא ומורחב מה-AI")
                        st.markdown(response_text)

    # --- מודול השוואה בין מספר נכסים פוטנציאליים ---
    elif mode == "השוואה בין מספר מניות כפוטנציאל השקעה":
        st.subheader("⚖️ השוואה בין מספר נכסים פוטנציאליים")
        tickers_list_raw = st.text_input("הזן סימולים להשוואה (מופרדים בפסיק, למשל: NVDA, AMD):", "NVDA, AMD")
        
        if st.button("בצע השוואה והפק המלצה", type="primary"):
            if not api_key:
                st.warning("⚠️ אנא הזן מפתח API בתפריט הצדדי")
            else:
                tickers = [t.strip().upper() for t in tickers_list_raw.split(",") if t.strip()]
                comparison_data = []
                
                with st.spinner("שולף נתוני אמת מורחבים עבור כל המניות להשוואה..."):
                    for t in tickers:
                        d = fetch_stock_advanced_engine(t)
                        if d:
                            existing_val = sum(item["shares"] * item["price"] for item in st.session_state.portfolio if item["ticker"] == t)
                            current_concen = (existing_val / st.session_state.total_portfolio_value) * 100 if st.session_state.total_portfolio_value > 0 else 0
                            potential_concen = ((existing_val + additional_capital) / st.session_state.total_portfolio_value) * 100 if st.session_state.total_portfolio_value > 0 else 0
                            
                            comparison_data.append({
                                "מניה": t, "מחיר נוכחי": f"${d['price']:.2f}", "סקטור": d["sector"], "בטא": d["beta"], 
                                "דירוג אנליסטים": str(d['analyst_rating']).upper(), "מחיר יעד": f"${d['target_price']}",
                                "מרחק משיא": f"{d['pct_from_high']:.1f}%", "תנודתיות": f"{d['volatility']:.1f}%",
                                "חשיפה לפני": f"{current_concen:.1f}%", "חשיפה אחרי": f"{potential_concen:.1f}%"
                            })
                
                if comparison_data:
                    st.write("### טבלת ריכוז והשוואה מורחבת")
                    st.dataframe(pd.DataFrame(comparison_data), use_container_width=True)
                else:
                    st.error("❌ לא נמצאו נתוני שוק עבור הסימולים שהוזנו.")
