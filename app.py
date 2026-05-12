"""Copywriter Agent — Streamlit UI multi-modalita`.

Tre tab principali:
  - Ads (Meta | Google | TikTok | LinkedIn)
  - Mail di conferma post-iscrizione
  - Mail di nurturing (sequenza intera | singola)

La sidebar condivide brand_voice + target_audience tra tutte le modalita`.
"""
from __future__ import annotations

import os
import traceback

import streamlit as st
from dotenv import load_dotenv

from dataclasses import asdict
from uuid import uuid4

from agent import ads as ads_mod
from agent import confirmation as conf_mod
from agent import nurturing as nurt_mod
from agent.store import SupabaseStore


# ── Config ─────────────────────────────────────────────────────────
load_dotenv()


def _secret(key: str, default: str = "") -> str:
    val = os.getenv(key)
    if val:
        return val
    try:
        return st.secrets.get(key, default)
    except (FileNotFoundError, AttributeError):
        return default


ANTHROPIC_API_KEY = _secret("ANTHROPIC_API_KEY")
APP_PASSWORD = _secret("APP_PASSWORD")

st.set_page_config(page_title="Copywriter Agent", layout="wide", page_icon="✍️")


# ── Password gate ──────────────────────────────────────────────────
def _password_gate() -> None:
    if not APP_PASSWORD:
        return
    if st.session_state.get("authed"):
        return
    st.title("✍️ Copywriter Agent")
    pw = st.text_input("Password", type="password", key="pw_input")
    if st.button("Entra"):
        if pw == APP_PASSWORD:
            st.session_state.authed = True
            st.rerun()
        else:
            st.error("Password errata")
    st.stop()


_password_gate()


# ── Session state ──────────────────────────────────────────────────
DEFAULT_STATE: dict[str, object] = {
    # Ads
    "ads_results": None,        # list[Ad]
    "ads_last_inputs": None,    # dict riusato per regenerate_one
    "ads_channel": "meta",
    # Confirmation mail
    "conf_results": None,
    "conf_last_inputs": None,
    # Nurturing
    "nurt_results": None,       # list[NurturingMail]
    "nurt_last_inputs": None,
    "nurt_mode": "sequence",
}
for k, v in DEFAULT_STATE.items():
    if k not in st.session_state:
        st.session_state[k] = v


def _reset_mod(prefix: str) -> None:
    """Azzera lo stato di una specifica modalita` (ads, conf, nurt)."""
    for k in DEFAULT_STATE:
        if k.startswith(prefix):
            st.session_state[k] = DEFAULT_STATE[k]


# ── Persistenza Supabase (cross-agent storage) ─────────────────────


def _store() -> SupabaseStore | None:
    """Cache lo SupabaseStore in session_state per non ricostruirlo a ogni rerun."""
    if "_supabase_store" not in st.session_state:
        try:
            st.session_state._supabase_store = SupabaseStore.from_env()
        except Exception:
            st.session_state._supabase_store = None
    return st.session_state._supabase_store


def _persist(
    *,
    subtype: str,
    title: str,
    payload: dict,
    preview: str,
    metadata: dict,
    session_id: str | None = None,
) -> str | None:
    """Best-effort save: ritorna l'id Supabase se ok, None altrimenti.

    Mostra un toast discreto in caso di errore — non blocca il flow."""
    store = _store()
    if store is None:
        return None
    try:
        saved = store.save_text_output(
            agent_type="copywriter",
            subtype=subtype,
            title=title,
            payload=payload,
            preview=preview,
            metadata=metadata,
            source_session_id=session_id,
        )
        return saved.id
    except Exception as e:
        st.toast(f"Salvataggio Supabase fallito: {e}", icon="⚠️")
        return None


# ── Sidebar ────────────────────────────────────────────────────────
def _sidebar() -> dict[str, str]:
    st.sidebar.header("⚙️ Setup condiviso")
    if not ANTHROPIC_API_KEY:
        st.sidebar.error(
            "Manca `ANTHROPIC_API_KEY`. Settala in `.env` (locale) o in "
            "Streamlit Cloud → Settings → Secrets."
        )

    target = st.sidebar.text_area(
        "Target audience (1 frase)",
        value=st.session_state.get("_sb_target", ""),
        placeholder=(
            "Es. imprenditori 35-55 con un'attivita` da 200-800k che hanno "
            "gia` provato Meta Ads e si sono bruciati"
        ),
        height=90,
        key="_sb_target",
    )
    voice = st.sidebar.text_area(
        "Brand voice (1 frase)",
        value=st.session_state.get("_sb_voice", ""),
        placeholder="Es. diretto, pragmatico, italiano semplice, no anglicismi",
        height=80,
        key="_sb_voice",
    )

    st.sidebar.divider()
    if st.sidebar.button("🔄 Reset totale", use_container_width=True):
        for k in list(DEFAULT_STATE):
            st.session_state[k] = DEFAULT_STATE[k]
        st.rerun()

    return {
        "target_audience": (target or "").strip(),
        "brand_voice": (voice or "").strip(),
    }


# ── Pagina Ads ─────────────────────────────────────────────────────
CHANNEL_LABELS = {
    "meta": "Meta (Facebook + Instagram)",
    "google": "Google Search (RSA)",
    "tiktok": "TikTok / Reels",
    "linkedin": "LinkedIn Sponsored",
}


def _render_ads_page(sidebar: dict[str, str]) -> None:
    st.subheader("📣 Ads — copy per Meta, Google, TikTok, LinkedIn")
    st.caption(
        "Ogni canale ha vincoli diversi (caratteri, struttura). L'agente li "
        "rispetta e produce varianti con angle diversi."
    )

    if st.session_state.ads_results is None:
        _ads_input_form(sidebar)
    else:
        _ads_output_panel(sidebar)


def _ads_input_form(sidebar: dict[str, str]) -> None:
    with st.form("ads_form"):
        cols = st.columns([2, 1, 1])
        channel = cols[0].selectbox(
            "Canale",
            options=list(CHANNEL_LABELS),
            index=list(CHANNEL_LABELS).index(st.session_state.ads_channel),
            format_func=lambda k: CHANNEL_LABELS[k],
        )
        n_variants = cols[1].slider(
            "Quante varianti?",
            min_value=ads_mod.MIN_VARIANTS,
            max_value=ads_mod.MAX_VARIANTS,
            value=5,
        )
        promise = cols[2].text_input(
            "Promessa (opzionale)",
            placeholder="Es. LIBERI COL MATTONE — 5k/mese in 90 giorni",
            help="Headline/USP gia` decisa, l'agente la usa come ancora.",
        )

        context = st.text_area(
            "📥 Context — offerta, target, pain, dream, prove, vincoli",
            value="",
            height=320,
            placeholder=(
                "Carica TUTTO. Piu` dai, meglio scrive.\n\n"
                "→ Cosa vendi (prodotto/servizio in 2-3 righe)\n"
                "→ Chi e` il prospect (eta`, ruolo, contesto, awareness)\n"
                "→ Pain attuale (le parole esatte che usa)\n"
                "→ Dream outcome (numeri, KPI concreti, sensazioni)\n"
                "→ Meccanismo unico (cosa rende l'offerta diversa)\n"
                "→ Prove (case study, testimonianze, dati)\n"
                "→ Vincoli (cosa NON dire, claim da evitare)\n"
                "→ Per Google: la KEYWORD principale che vuoi presidiare"
            ),
        )
        references = st.text_area(
            "📚 Reference — esempi/strutture che l'agente deve studiare",
            value="",
            height=140,
            placeholder=(
                "Opzionale. Esempi di ad che hanno performato bene, "
                "strutture che ti piacciono, frasi da riprendere."
            ),
        )
        extra = st.text_input(
            "Istruzioni extra (opzionale)",
            placeholder="Es. 'evita garanzie monetarie', 'tono piu` provocatorio'",
        )

        submitted = st.form_submit_button(
            "✨ Genera ads",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    if not context.strip():
        st.error("Devi compilare il **Context**.")
        return
    if not ANTHROPIC_API_KEY:
        st.error("Manca `ANTHROPIC_API_KEY`.")
        return

    with st.spinner(f"Genero {n_variants} varianti per {CHANNEL_LABELS[channel]}…"):
        try:
            results = ads_mod.write_ads(
                api_key=ANTHROPIC_API_KEY,
                channel=channel,
                context=context,
                references=references,
                target_audience=sidebar["target_audience"],
                brand_voice=sidebar["brand_voice"],
                promise=promise,
                n_variants=n_variants,
                extra_instructions=extra,
            )
            st.session_state.ads_results = results
            st.session_state.ads_channel = channel
            st.session_state.ads_last_inputs = {
                "channel": channel,
                "context": context,
                "references": references,
                "target_audience": sidebar["target_audience"],
                "brand_voice": sidebar["brand_voice"],
                "promise": promise,
            }
            session_id = uuid4().hex
            payload = {"variants": [asdict(a) for a in results]}
            first = results[0] if results else None
            preview_text = ""
            if isinstance(first, ads_mod.MetaAd):
                preview_text = first.primary_text
            elif isinstance(first, ads_mod.GoogleAd):
                preview_text = " | ".join(first.headlines[:3])
            elif isinstance(first, ads_mod.TikTokAd):
                preview_text = first.hook
            elif isinstance(first, ads_mod.LinkedInAd):
                preview_text = first.headline
            _persist(
                subtype=f"ads_{channel}",
                title=(
                    f"{CHANNEL_LABELS[channel]} — {len(results)} varianti"
                    + (f" · {promise}" if promise else "")
                ),
                payload=payload,
                preview=preview_text,
                metadata={
                    "channel": channel,
                    "target_audience": sidebar["target_audience"],
                    "brand_voice": sidebar["brand_voice"],
                    "promise": promise,
                    "n_variants": len(results),
                },
                session_id=session_id,
            )
            st.rerun()
        except Exception as e:
            st.error(f"Generazione fallita: {e}")
            st.caption(traceback.format_exc())


def _render_ad_card(ad: ads_mod.Ad, index: int, channel: str) -> None:
    """Render di una variante ads in base al canale."""
    if isinstance(ad, ads_mod.MetaAd):
        st.markdown(f"**Variante #{index + 1} · Meta** — _{ad.angle or '—'}_")
        st.markdown(
            f"<div style='background:#f4f6f8; padding:14px; border-radius:8px;"
            f" border-left:3px solid #1877f2;'>"
            f"<div style='font-size:0.85rem; color:#555; margin-bottom:6px;'>"
            f"PRIMARY TEXT ({len(ad.primary_text)} char)</div>"
            f"<div>{ad.primary_text.replace(chr(10), '<br/>')}</div>"
            f"<div style='margin-top:10px; font-weight:700;'>"
            f"{ad.headline} <span style='color:#888; font-size:0.8rem;'>"
            f"({len(ad.headline)}/40)</span></div>"
            f"<div style='color:#555;'>{ad.description}"
            f"<span style='color:#888; font-size:0.8rem;'>"
            f" ({len(ad.description)}/30)</span></div>"
            f"<div style='margin-top:8px; display:inline-block; padding:4px 10px;"
            f" background:#1877f2; color:#fff; border-radius:4px;"
            f" font-size:0.85rem;'>{ad.cta}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    elif isinstance(ad, ads_mod.GoogleAd):
        st.markdown(f"**Variante #{index + 1} · Google RSA** — _{ad.angle or '—'}_")
        with st.expander(f"📑 {len(ad.headlines)} headlines / "
                         f"{len(ad.descriptions)} descriptions", expanded=True):
            st.markdown("**Headlines** (max 30 char ognuna):")
            for i, h in enumerate(ad.headlines, 1):
                over = "🔴" if len(h) > 30 else "✓"
                st.markdown(f"{over} `{len(h):>2}` — H{i}: {h}")
            st.markdown("**Descriptions** (max 90 char):")
            for i, d in enumerate(ad.descriptions, 1):
                over = "🔴" if len(d) > 90 else "✓"
                st.markdown(f"{over} `{len(d):>2}` — D{i}: {d}")
            if ad.paths:
                st.markdown("**Paths**: " + " / ".join(f"`/{p}`" for p in ad.paths))
    elif isinstance(ad, ads_mod.TikTokAd):
        st.markdown(f"**Variante #{index + 1} · TikTok/Reels** — _{ad.angle or '—'}_")
        st.markdown(
            f"<div style='background:#fafafa; padding:14px; border-radius:8px;"
            f" border-left:3px solid #000;'>"
            f"<div style='font-weight:700; font-size:1.1rem; "
            f"margin-bottom:6px;'>🎬 HOOK (0-3s)</div>"
            f"<div style='font-size:1.05rem;'>{ad.hook}</div>"
            f"<div style='margin-top:14px; font-weight:700;'>BODY (parlato)</div>"
            f"<div>{ad.body.replace(chr(10), '<br/>')}</div>"
            f"<div style='margin-top:14px; font-weight:700;'>CTA finale</div>"
            f"<div>{ad.cta_verbal}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**Caption:** {ad.caption}")
        if ad.hashtags:
            st.caption(" ".join(f"#{h}" for h in ad.hashtags))
    elif isinstance(ad, ads_mod.LinkedInAd):
        st.markdown(f"**Variante #{index + 1} · LinkedIn** — _{ad.angle or '—'}_")
        st.markdown(
            f"<div style='background:#eaf4ff; padding:14px; border-radius:8px;"
            f" border-left:3px solid #0a66c2;'>"
            f"<div style='font-weight:700; font-size:1.05rem; "
            f"margin-bottom:6px;'>{ad.headline} "
            f"<span style='color:#888; font-size:0.8rem;'>"
            f"({len(ad.headline)} char)</span></div>"
            f"<div>{ad.body.replace(chr(10), '<br/>')}</div>"
            f"<div style='margin-top:8px; display:inline-block; padding:4px 10px;"
            f" background:#0a66c2; color:#fff; border-radius:4px;"
            f" font-size:0.85rem;'>{ad.cta}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    if ad.rationale:
        with st.expander("Perche` funziona"):
            st.markdown(ad.rationale)


def _ads_output_panel(sidebar: dict[str, str]) -> None:
    results = st.session_state.ads_results
    last = st.session_state.ads_last_inputs or {}
    channel = last.get("channel", "meta")

    st.success(
        f"Generate **{len(results)}** varianti per {CHANNEL_LABELS[channel]}."
    )

    cols = st.columns([1, 1, 4])
    if cols[0].button("⬅️ Nuovo brief", key="ads_new_brief"):
        _reset_mod("ads_")
        st.rerun()
    if cols[1].button("🔁 Rigenera tutto", key="ads_regen_all"):
        st.session_state.ads_results = None
        st.rerun()

    st.divider()

    for i, ad in enumerate(results):
        with st.container(border=True):
            _render_ad_card(ad, i, channel)

            with st.expander("🔄 Rigenera questa variante con feedback"):
                fb = st.text_area(
                    "Cosa cambiare?",
                    placeholder="Es. 'troppo lungo, taglia il primary text'",
                    key=f"ads_fb_{i}",
                    height=80,
                )
                if st.button(
                    "🪄 Rigenera", key=f"ads_regen_{i}", disabled=not fb.strip()
                ):
                    with st.spinner("Rigenerazione…"):
                        try:
                            new_ad = ads_mod.regenerate_one(
                                api_key=ANTHROPIC_API_KEY,
                                channel=channel,
                                original=ad,
                                feedback=fb,
                                context=last.get("context", ""),
                                references=last.get("references", ""),
                                target_audience=last.get("target_audience", ""),
                                brand_voice=last.get("brand_voice", ""),
                                promise=last.get("promise", ""),
                            )
                            st.session_state.ads_results[i] = new_ad
                            st.rerun()
                        except Exception as e:
                            st.error(f"Rigenerazione fallita: {e}")


# ── Pagina Mail di conferma ────────────────────────────────────────


def _render_confirmation_page(sidebar: dict[str, str]) -> None:
    st.subheader("📧 Mail di conferma post-iscrizione")
    st.caption(
        "La mail che chi si iscrive riceve subito. Consegna il lead magnet, "
        "rassicura, alza l'aspettativa per la sequenza di nurturing."
    )

    if st.session_state.conf_results is None:
        _conf_input_form(sidebar)
    else:
        _conf_output_panel(sidebar)


def _conf_input_form(sidebar: dict[str, str]) -> None:
    with st.form("conf_form"):
        cols = st.columns([2, 2, 1])
        lead_magnet = cols[0].text_input(
            "Lead magnet (cosa ha richiesto)",
            placeholder="Es. PDF 'Le 7 leve del marketing immobiliare'",
        )
        sender = cols[1].text_input(
            "Sender (chi firma)",
            placeholder="Es. Salvo Trifiro, founder Leone Master School",
        )
        n_variants = cols[2].slider(
            "Varianti",
            min_value=conf_mod.MIN_VARIANTS,
            max_value=conf_mod.MAX_VARIANTS,
            value=3,
        )

        promise = st.text_input(
            "Promessa del funnel (cosa hanno letto nella landing)",
            placeholder="Es. 5 nuovi clienti in 90 giorni senza ads",
        )
        context = st.text_area(
            "📥 Context — offerta, target, tono",
            value="",
            height=240,
            placeholder=(
                "→ Cosa vende il funnel (il prodotto finale dietro al lead magnet)\n"
                "→ Chi si iscrive (target, awareness, perche` ha richiesto il magnet)\n"
                "→ Cosa farai dopo (anteprima della sequenza di nurturing)\n"
                "→ Vincoli (claim da evitare, parole proibite)"
            ),
        )
        references = st.text_area(
            "📚 Reference — esempi di mail che funzionano",
            value="",
            height=120,
        )
        extra = st.text_input(
            "Istruzioni extra (opzionale)",
            placeholder="Es. 'tono molto amichevole', 'inserisci un PS con domanda'",
        )

        submitted = st.form_submit_button(
            "✨ Genera mail di conferma",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return
    if not context.strip():
        st.error("Devi compilare il **Context**.")
        return
    if not ANTHROPIC_API_KEY:
        st.error("Manca `ANTHROPIC_API_KEY`.")
        return

    with st.spinner(f"Genero {n_variants} varianti…"):
        try:
            results = conf_mod.write_confirmation_mails(
                api_key=ANTHROPIC_API_KEY,
                context=context,
                references=references,
                target_audience=sidebar["target_audience"],
                brand_voice=sidebar["brand_voice"],
                lead_magnet=lead_magnet,
                promise=promise,
                sender=sender,
                n_variants=n_variants,
                extra_instructions=extra,
            )
            st.session_state.conf_results = results
            st.session_state.conf_last_inputs = {
                "context": context,
                "references": references,
                "target_audience": sidebar["target_audience"],
                "brand_voice": sidebar["brand_voice"],
                "lead_magnet": lead_magnet,
                "promise": promise,
                "sender": sender,
            }
            payload = {"variants": [asdict(m) for m in results]}
            first = results[0] if results else None
            preview_text = (first.subject + " — " + first.body[:200]) if first else ""
            _persist(
                subtype="confirmation_mail",
                title=(
                    f"Mail conferma — {lead_magnet or 'lead magnet'}"
                    + f" ({len(results)} varianti)"
                ),
                payload=payload,
                preview=preview_text,
                metadata={
                    "lead_magnet": lead_magnet,
                    "promise": promise,
                    "sender": sender,
                    "target_audience": sidebar["target_audience"],
                    "n_variants": len(results),
                },
                session_id=uuid4().hex,
            )
            st.rerun()
        except Exception as e:
            st.error(f"Generazione fallita: {e}")
            st.caption(traceback.format_exc())


def _conf_output_panel(sidebar: dict[str, str]) -> None:
    results: list[conf_mod.ConfirmationMail] = st.session_state.conf_results
    last = st.session_state.conf_last_inputs or {}

    st.success(f"Generate **{len(results)}** varianti.")

    cols = st.columns([1, 1, 4])
    if cols[0].button("⬅️ Nuovo brief", key="conf_new_brief"):
        _reset_mod("conf_")
        st.rerun()
    if cols[1].button("🔁 Rigenera tutto", key="conf_regen_all"):
        st.session_state.conf_results = None
        st.rerun()

    st.divider()

    for i, mail in enumerate(results):
        with st.container(border=True):
            st.markdown(f"**Variante #{i + 1}** — tono _{mail.tone or '—'}_")
            st.markdown(f"**Subject:** {mail.subject}")
            st.caption(f"Preview: {mail.preview}")
            st.markdown(
                f"<div style='background:#f7f7f7; padding:12px; "
                f"border-radius:6px; white-space:pre-wrap;'>{mail.body}</div>",
                unsafe_allow_html=True,
            )
            if mail.signature:
                st.markdown(
                    f"<div style='background:#fafafa; padding:10px; "
                    f"border-radius:6px; margin-top:6px; "
                    f"white-space:pre-wrap; color:#444; font-size:0.95rem;'>"
                    f"{mail.signature}</div>",
                    unsafe_allow_html=True,
                )
            if mail.rationale:
                with st.expander("Perche` funziona"):
                    st.markdown(mail.rationale)

            with st.expander("🔄 Rigenera con feedback"):
                fb = st.text_area(
                    "Cosa cambiare?",
                    key=f"conf_fb_{i}",
                    height=80,
                )
                if st.button(
                    "🪄 Rigenera",
                    key=f"conf_regen_{i}",
                    disabled=not fb.strip(),
                ):
                    with st.spinner("Rigenerazione…"):
                        try:
                            new_mail = conf_mod.regenerate_one(
                                api_key=ANTHROPIC_API_KEY,
                                original=mail,
                                feedback=fb,
                                context=last.get("context", ""),
                                references=last.get("references", ""),
                                target_audience=last.get("target_audience", ""),
                                brand_voice=last.get("brand_voice", ""),
                                lead_magnet=last.get("lead_magnet", ""),
                                promise=last.get("promise", ""),
                                sender=last.get("sender", ""),
                            )
                            st.session_state.conf_results[i] = new_mail
                            st.rerun()
                        except Exception as e:
                            st.error(f"Rigenerazione fallita: {e}")


# ── Pagina Nurturing ───────────────────────────────────────────────


NURTURING_ROLES = [
    "bonding",
    "pain-agitation",
    "mechanism",
    "proof",
    "anti-objection",
    "urgency-offer",
]


def _render_nurturing_page(sidebar: dict[str, str]) -> None:
    st.subheader("🌱 Mail di nurturing")
    st.caption(
        "Sequenza di nurturing per chi si e` iscritto al funnel. Puoi generare "
        "l'intera sequenza in un colpo, o una singola mail per un ruolo specifico."
    )

    if st.session_state.nurt_results is None:
        _nurt_input_form(sidebar)
    else:
        _nurt_output_panel(sidebar)


def _nurt_input_form(sidebar: dict[str, str]) -> None:
    mode = st.radio(
        "Modalita`",
        options=["sequence", "single"],
        format_func=lambda m: (
            "📚 Sequenza intera" if m == "sequence" else "✉️ Singola mail"
        ),
        horizontal=True,
        key="_nurt_mode_radio",
        index=0 if st.session_state.nurt_mode == "sequence" else 1,
    )
    st.session_state.nurt_mode = mode

    with st.form(f"nurt_form_{mode}"):
        cols = st.columns(3)
        lead_magnet = cols[0].text_input(
            "Lead magnet appena consegnato",
            placeholder="Es. PDF '7 leve del marketing immobiliare'",
        )
        sender = cols[1].text_input(
            "Sender (firma)",
            placeholder="Es. Salvo Trifiro, founder LMS",
        )
        offer = cols[2].text_input(
            "Offerta finale (la chiusura)",
            placeholder="Es. call gratuita con advisor",
        )

        promise = st.text_input(
            "Promessa del funnel",
            placeholder="Es. LIBERI COL MATTONE — 5k/mese in 90 giorni",
        )

        if mode == "sequence":
            cols2 = st.columns(2)
            n_mails = cols2[0].slider(
                "Quante mail?",
                min_value=nurt_mod.MIN_SEQUENCE,
                max_value=nurt_mod.MAX_SEQUENCE,
                value=5,
            )
            cadence = cols2[1].slider(
                "Distribuite su quanti giorni?",
                min_value=1,
                max_value=21,
                value=7,
            )
            role = ""
            day = 0
        else:
            cols2 = st.columns([2, 1])
            role = cols2[0].selectbox(
                "Ruolo della mail",
                options=NURTURING_ROLES,
            )
            day = cols2[1].number_input(
                "Day (0 = non specificato)",
                min_value=0,
                max_value=30,
                value=0,
            )
            n_mails = 0
            cadence = 0

        context = st.text_area(
            "📥 Context — offerta, target, prove, vincoli",
            value="",
            height=260,
            placeholder=(
                "→ Cosa vendi (offerta finale)\n"
                "→ Chi si e` iscritto (target, awareness, perche`)\n"
                "→ Pain del target (parole esatte)\n"
                "→ Meccanismo unico\n"
                "→ Prove (case study, dati, testimonial)\n"
                "→ Vincoli"
            ),
        )
        references = st.text_area(
            "📚 Reference — esempi/strutture ispirazionali",
            value="",
            height=120,
        )
        extra = st.text_input(
            "Istruzioni extra (opzionale)",
            placeholder="Es. 'punta su storytelling 1ma persona'",
        )

        submitted = st.form_submit_button(
            "✨ Genera",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return
    if not context.strip():
        st.error("Devi compilare il **Context**.")
        return
    if not ANTHROPIC_API_KEY:
        st.error("Manca `ANTHROPIC_API_KEY`.")
        return

    last_inputs = {
        "mode": mode,
        "context": context,
        "references": references,
        "target_audience": sidebar["target_audience"],
        "brand_voice": sidebar["brand_voice"],
        "lead_magnet": lead_magnet,
        "promise": promise,
        "offer": offer,
        "sender": sender,
    }

    try:
        if mode == "sequence":
            with st.spinner(f"Genero {n_mails} mail di nurturing…"):
                results = nurt_mod.write_sequence(
                    api_key=ANTHROPIC_API_KEY,
                    context=context,
                    references=references,
                    target_audience=sidebar["target_audience"],
                    brand_voice=sidebar["brand_voice"],
                    lead_magnet=lead_magnet,
                    promise=promise,
                    offer=offer,
                    sender=sender,
                    n_mails=n_mails,
                    cadence_days=cadence,
                    extra_instructions=extra,
                )
            st.session_state.nurt_results = results
        else:
            with st.spinner(f"Genero mail '{role}'…"):
                mail = nurt_mod.write_single(
                    api_key=ANTHROPIC_API_KEY,
                    role=role,
                    context=context,
                    references=references,
                    target_audience=sidebar["target_audience"],
                    brand_voice=sidebar["brand_voice"],
                    lead_magnet=lead_magnet,
                    promise=promise,
                    offer=offer,
                    sender=sender,
                    day=int(day),
                    extra_instructions=extra,
                )
            st.session_state.nurt_results = [mail]
        st.session_state.nurt_last_inputs = last_inputs

        results_for_save = st.session_state.nurt_results
        if results_for_save:
            payload = {"mails": [asdict(m) for m in results_for_save]}
            first = results_for_save[0]
            preview_text = first.subject + " — " + first.body[:200]
            sub = "nurturing_sequence" if mode == "sequence" else "nurturing_single"
            title = (
                f"Nurturing — {lead_magnet or 'lead magnet'}"
                f" ({len(results_for_save)} mail)"
                if mode == "sequence"
                else f"Nurturing — singola '{role}'"
            )
            _persist(
                subtype=sub,
                title=title,
                payload=payload,
                preview=preview_text,
                metadata={
                    "mode": mode,
                    "lead_magnet": lead_magnet,
                    "promise": promise,
                    "offer": offer,
                    "sender": sender,
                    "n_mails": len(results_for_save),
                    **({"role": role} if mode == "single" else {}),
                },
                session_id=uuid4().hex,
            )
        st.rerun()
    except Exception as e:
        st.error(f"Generazione fallita: {e}")
        st.caption(traceback.format_exc())


def _nurt_output_panel(sidebar: dict[str, str]) -> None:
    results: list[nurt_mod.NurturingMail] = st.session_state.nurt_results
    last = st.session_state.nurt_last_inputs or {}

    st.success(f"Generate **{len(results)}** mail.")

    cols = st.columns([1, 1, 4])
    if cols[0].button("⬅️ Nuovo brief", key="nurt_new_brief"):
        _reset_mod("nurt_")
        st.rerun()
    if cols[1].button("🔁 Rigenera tutto", key="nurt_regen_all"):
        st.session_state.nurt_results = None
        st.rerun()

    st.divider()

    for i, mail in enumerate(results):
        with st.container(border=True):
            header = f"**Mail #{i + 1}**"
            if mail.day:
                header += f" · Day {mail.day}"
            if mail.role:
                header += f" · _{mail.role}_"
            st.markdown(header)
            st.markdown(f"**Subject:** {mail.subject}")
            st.caption(f"Preview: {mail.preview}")
            st.markdown(
                f"<div style='background:#f7f7f7; padding:12px; "
                f"border-radius:6px; white-space:pre-wrap;'>{mail.body}</div>",
                unsafe_allow_html=True,
            )
            if mail.signature:
                st.markdown(
                    f"<div style='background:#fafafa; padding:10px; "
                    f"border-radius:6px; margin-top:6px; "
                    f"white-space:pre-wrap; color:#444; font-size:0.95rem;'>"
                    f"{mail.signature}</div>",
                    unsafe_allow_html=True,
                )
            if mail.cta:
                st.markdown(f"**CTA:** {mail.cta}")
            if mail.rationale:
                with st.expander("Perche` funziona qui nella sequenza"):
                    st.markdown(mail.rationale)

            with st.expander("🔄 Rigenera con feedback"):
                fb = st.text_area(
                    "Cosa cambiare?",
                    key=f"nurt_fb_{i}",
                    height=80,
                )
                if st.button(
                    "🪄 Rigenera",
                    key=f"nurt_regen_{i}",
                    disabled=not fb.strip(),
                ):
                    with st.spinner("Rigenerazione…"):
                        try:
                            new_mail = nurt_mod.regenerate_one(
                                api_key=ANTHROPIC_API_KEY,
                                original=mail,
                                feedback=fb,
                                context=last.get("context", ""),
                                references=last.get("references", ""),
                                target_audience=last.get("target_audience", ""),
                                brand_voice=last.get("brand_voice", ""),
                                lead_magnet=last.get("lead_magnet", ""),
                                promise=last.get("promise", ""),
                                offer=last.get("offer", ""),
                                sender=last.get("sender", ""),
                            )
                            st.session_state.nurt_results[i] = new_mail
                            st.rerun()
                        except Exception as e:
                            st.error(f"Rigenerazione fallita: {e}")


# ── Top-level rendering ────────────────────────────────────────────


def _main() -> None:
    sidebar = _sidebar()

    st.title("✍️ Copywriter Agent")
    st.caption(
        "Copywriter senior per **Ads** (Meta, Google, TikTok, LinkedIn), "
        "**mail di conferma** post-iscrizione e **sequenze di nurturing**. "
        "Un'unica codebase, tre modalita`."
    )

    tab_ads, tab_conf, tab_nurt = st.tabs(
        ["📣 Ads", "📧 Mail di conferma", "🌱 Nurturing"]
    )
    with tab_ads:
        _render_ads_page(sidebar)
    with tab_conf:
        _render_confirmation_page(sidebar)
    with tab_nurt:
        _render_nurturing_page(sidebar)


_main()
