"""Streamlit app: value bets, bet log and statistics.

Start:  streamlit run src/app.py
Demo:   choose "Demo" in the sidebar (fake data is generated automatically).
Password (optional): set APP_PASSWORD in .streamlit/secrets.toml or in the
Streamlit Cloud app settings -> Secrets. Without it the app is open.
"""

import hmac
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import altair as alt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src import betlog, config, live, oddsdb  # noqa: E402
from src.demo import DEMO_DIR, generate  # noqa: E402

OUT_NAME = {"h": "1", "d": "X", "a": "2"}
LEAGUE_NAME = {
    "soccer_epl": "Premier League", "soccer_efl_champ": "Championship",
    "soccer_spain_la_liga": "La Liga", "soccer_italy_serie_a": "Serie A",
    "soccer_germany_bundesliga": "Bundesliga", "soccer_france_ligue_one": "Ligue 1",
    "soccer_sweden_allsvenskan": "Allsvenskan", "soccer_sweden_superettan": "Superettan",
    "soccer_norway_eliteserien": "Eliteserien", "soccer_denmark_superliga": "Superligaen",
}

st.set_page_config(page_title="Value-betting", page_icon="⚽", layout="wide")


def require_password() -> None:
    """Stop the app until the right password is given (only if APP_PASSWORD is set)."""
    try:
        password = st.secrets.get("APP_PASSWORD")
    except Exception:  # no secrets file at all
        password = None
    if not password or st.session_state.get("authenticated"):
        return
    st.title("⚽ Value-betting")
    entered = st.text_input("Lösenord", type="password")
    if entered and hmac.compare_digest(entered, str(password)):
        st.session_state["authenticated"] = True
        st.rerun()
    elif entered:
        st.error("Fel lösenord.")
    st.stop()


require_password()


# ---------------------------------------------------------------- data

def paths(source: str) -> dict:
    if source == "Demo":
        return {"snapshots": DEMO_DIR / "snapshots", "db": DEMO_DIR / "odds.sqlite",
                "api_log": DEMO_DIR / "api_calls.csv", "bets": DEMO_DIR / "bets.csv"}
    return {"snapshots": config.SNAPSHOT_DIR, "db": config.DB_PATH, "api_log": config.API_LOG,
            "bets": betlog.bets_path()}


def _fingerprint(folder: Path) -> tuple:
    files = list(Path(folder).rglob("*.json.gz")) if Path(folder).exists() else []
    return len(files), max((f.stat().st_mtime for f in files), default=0)


@st.cache_data(show_spinner="Bygger databasen från hämtade odds …")
def load_prices(snapshots: str, db: str, api_log: str, _fp: tuple) -> pd.DataFrame:
    con = oddsdb.build(Path(db), Path(snapshots), Path(api_log))
    return oddsdb.price_table(con)


# ---------------------------------------------------------------- sidebar

st.sidebar.title("⚽ Value-betting")
has_real = _fingerprint(config.SNAPSHOT_DIR)[0] > 0
source = st.sidebar.radio("Data", ["Riktig", "Demo"], horizontal=True, index=0 if has_real else 1,
                          help="Demo = påhittade lag och odds, bara för att prova sidan.")
P = paths(source)
if source == "Demo" and not P["snapshots"].exists():
    with st.spinner("Skapar demodata …"):
        generate()
bankroll = st.sidebar.number_input("Startkassa (kr)", min_value=100, value=1000, step=100)
threshold = st.sidebar.slider("Minsta value", 0.0, 0.10, config.VALUE_THRESHOLD, 0.01, format="%.2f")
st.sidebar.caption(f"Insats = kvarts-Kelly, högst {config.MAX_STAKE_SHARE:.0%} av kassan.")
st.sidebar.markdown("---")
st.sidebar.caption("Verktyget är för analys. Spela bara för pengar du har råd att förlora. "
                   "Stödlinjen: 020-81 91 00.")

if source == "Demo":
    st.warning("**DEMOLÄGE** – allt nedan är påhittat (fiktiva lag, slumpade odds och resultat).")

prices = load_prices(str(P["snapshots"]), str(P["db"]), str(P["api_log"]), _fingerprint(P["snapshots"]))
bets = betlog.load_bets(P["bets"])
closing = live.closing_fair(prices) if len(prices) else None

tab_value, tab_log, tab_stats = st.tabs(["📋 Value-spel", "📝 Spellogg", "📈 Statistik"])

# ---------------------------------------------------------------- value bets

with tab_value:
    st.subheader("Value-spel i senaste hämtningen")
    if prices.empty:
        st.info("Inga odds hämtade än. När insamlingen (GitHub Actions) har kört dyker spelen upp här.")
    else:
        now = pd.Timestamp.now(tz="UTC")
        s = live.signals(prices, threshold)
        latest = s.groupby("event_id")["snapshot_id"].transform("max") == s["snapshot_id"]
        s = s[latest & (s["commence_time"] > now)].copy()
        s["stake_kr"] = (s["stake_share"] * bankroll).round(0)
        if s.empty:
            st.info("Inga spel över tröskeln just nu.")
        else:
            view = pd.DataFrame({
                "Avspark": s["commence_time"].dt.tz_convert("Europe/Stockholm").dt.strftime("%a %d/%m %H:%M"),
                "Liga": s["sport"].map(LEAGUE_NAME).fillna(s["sport"]),
                "Match": s["home"] + " – " + s["away"],
                "Spel": s["outcome"].map(OUT_NAME),
                "Bolag": s["book"],
                "Odds": s["odds"],
                "Rättvist odds": s["fair_odds"].round(2),
                "Value": s["value"],
                "Insats (kr)": s["stake_kr"],
                "Hämtat": s["fetched_at"].dt.tz_convert("Europe/Stockholm").dt.strftime("%d/%m %H:%M"),
            })
            st.dataframe(view, hide_index=True, use_container_width=True,
                         column_config={"Value": st.column_config.NumberColumn(format="percent"),
                                        "Odds": st.column_config.NumberColumn(format="%.2f"),
                                        "Rättvist odds": st.column_config.NumberColumn(format="%.2f"),
                                        "Insats (kr)": st.column_config.NumberColumn(format="%.0f")})

            st.markdown("#### Registrera ett spel du har lagt")
            labels = [f"{r.home} – {r.away} · {OUT_NAME[r.outcome]} · {r.book} @ {r.odds:.2f}"
                      for r in s.itertuples()]
            with st.form("add_bet"):
                i = st.selectbox("Spel", range(len(s)), format_func=lambda k: labels[k])
                r = s.iloc[i]
                c1, c2 = st.columns(2)
                odds = c1.number_input("Odds du fick", min_value=1.01, value=float(r["odds"]), step=0.01)
                stake = c2.number_input("Insats (kr)", min_value=1.0, value=float(max(r["stake_kr"], 1)), step=1.0)
                if st.form_submit_button("Spara i spelloggen"):
                    bets = betlog.add_bet(bets, event_id=r["event_id"], sport=r["sport"],
                                          match=f"{r['home']} – {r['away']}", commence_time=r["commence_time"],
                                          outcome=r["outcome"], book=r["book"], odds=odds, stake=stake,
                                          fair_odds=r["fair_odds"])
                    betlog.save_bets(bets, P["bets"])
                    st.success("Sparat!")

# ---------------------------------------------------------------- bet log

with tab_log:
    st.subheader("Spellogg")
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Ladda ner spelloggen (CSV)", bets.to_csv(index=False).encode("utf-8"),
                       file_name="bets.csv", mime="text/csv", disabled=bets.empty,
                       help="Spara en kopia ofta – på Streamlit Cloud kan filer försvinna när appen startas om.")
    up = c2.file_uploader("⬆️ Läs in en sparad spellogg", type="csv", label_visibility="collapsed")
    if up is not None and st.session_state.get("uploaded") != up.file_id:
        try:
            tmp = P["bets"].with_suffix(".upload.csv")
            tmp.write_bytes(up.getvalue())
            restored = betlog.load_bets(tmp)
            tmp.unlink()
            betlog.save_bets(restored, P["bets"])
            st.session_state["uploaded"] = up.file_id
            st.success(f"Läste in {len(restored)} spel.")
            st.rerun()
        except Exception as e:
            st.error(f"Kunde inte läsa filen: {e}")
    if bets.empty:
        st.info("Inga spel registrerade än. Lägg till från fliken Value-spel.")
    else:
        ev = betlog.evaluate(bets, closing)
        show = ev.assign(
            avspark=ev["commence_time"].dt.tz_convert("Europe/Stockholm").dt.strftime("%d/%m %H:%M"),
            spel=ev["outcome"].map(OUT_NAME))[
            ["bet_id", "avspark", "match", "spel", "book", "odds", "stake", "status", "profit", "clv", "note"]]
        edited = st.data_editor(
            show, hide_index=True, use_container_width=True,
            disabled=[c for c in show.columns if c not in ("status", "note")],
            column_config={
                "bet_id": st.column_config.NumberColumn("#"),
                "avspark": "Avspark", "match": "Match", "spel": "Spel", "book": "Bolag",
                "odds": st.column_config.NumberColumn("Odds", format="%.2f"),
                "note": st.column_config.TextColumn("Anteckning"),
                "status": st.column_config.SelectboxColumn("Status", options=betlog.STATUSES,
                                                           help="open = ej avgjort, void = insatsen tillbaka"),
                "profit": st.column_config.NumberColumn("Vinst (kr)", format="%.0f"),
                "clv": st.column_config.NumberColumn("CLV", format="percent"),
                "stake": st.column_config.NumberColumn("Insats", format="%.0f"),
            })
        if st.button("Spara ändringar"):
            out = bets.copy()
            out["status"] = edited["status"].to_numpy()
            out["note"] = edited["note"].fillna("").to_numpy()
            betlog.save_bets(out, P["bets"])
            st.success("Sparat!")
            st.rerun()

# ---------------------------------------------------------------- statistics

with tab_stats:
    st.subheader("Mina spel")
    ev = betlog.evaluate(bets, closing)
    s = betlog.summary(ev, bankroll)
    c = st.columns(5)
    c[0].metric("Avgjorda spel", f"{s['settled']}", help=f"{s['open']} spel är fortfarande öppna")
    c[1].metric("Vinst", f"{s['profit']:+.0f} kr")
    c[2].metric("ROI", "–" if np.isnan(s["roi"]) else f"{s['roi']:+.1%}")
    c[3].metric("Snitt-CLV", "–" if pd.isna(s["avg_clv"]) else f"{s['avg_clv']:+.1%}",
                help="Bästa måttet på om du får bra odds. Positivt över tid = verkligt övertag.")
    c[4].metric("Kassa", f"{s['bankroll']:.0f} kr")
    curve = betlog.bankroll_curve(ev, bankroll)
    if len(curve) > 1:
        curve = pd.concat([pd.DataFrame({"date": [curve["date"].iloc[0] - pd.Timedelta(hours=1)],
                                         "bankroll": [float(bankroll)]}), curve])
        chart = alt.Chart(curve).mark_line(strokeWidth=2).encode(
            x=alt.X("date:T", title=None, axis=alt.Axis(format="%d %b")),
            y=alt.Y("bankroll:Q", title="Kassa (kr)", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("date:T", title="Datum", format="%d %b %H:%M"),
                     alt.Tooltip("bankroll:Q", title="Kassa", format=".0f")])
        rule = alt.Chart(pd.DataFrame({"y": [bankroll]})).mark_rule(strokeDash=[4, 4], opacity=0.5).encode(y="y:Q")
        st.altair_chart(chart + rule, use_container_width=True)
    if s["settled"] and s["settled"] < 300:
        st.caption(f"Med {s['settled']} spel är ROI mest slump. CLV säger mer tills du har några hundra spel.")

    st.subheader("Alla signaler (oavsett om du spelade)")
    st.caption("Mäter om svenska bolags odds slår Pinnacles stängningsodds – kärnfrågan från fas 2.")
    if prices.empty:
        st.info("Ingen data än.")
    else:
        c = live.clv_table(prices).dropna(subset=["clv"])
        if c.empty:
            st.info("Inga avslutade signaler med stängningsodds än.")
        else:
            se = c["clv"].std(ddof=1) / np.sqrt(len(c)) if len(c) > 1 else np.nan
            k = st.columns(3)
            k[0].metric("Signaler", len(c))
            k[1].metric("Snitt-CLV", f"{c['clv'].mean():+.2%}")
            k[2].metric("95 % intervall", f"{c['clv'].mean() - 1.96 * se:+.1%} … {c['clv'].mean() + 1.96 * se:+.1%}")
            g = c.groupby("book").agg(Signaler=("clv", "size"), Snitt_CLV=("clv", "mean"),
                                      Snitt_value=("value", "mean")).reset_index().rename(columns={"book": "Bolag"})
            st.dataframe(g, hide_index=True, use_container_width=True,
                         column_config={"Snitt_CLV": st.column_config.NumberColumn("Snitt-CLV", format="percent"),
                                        "Snitt_value": st.column_config.NumberColumn("Snitt-value", format="percent")})
    if Path(P["api_log"]).exists():
        log = pd.read_csv(P["api_log"])
        last = log.dropna(subset=["remaining"]).tail(1)
        if len(last):
            st.caption(f"API-credits kvar denna månad: {int(last['remaining'].iloc[0])}")
