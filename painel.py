# Medidor: registrador contínuo de temperatura e umidade para laboratório
# Copyright (C) 2026 Universidade Federal do Paraná (UFPR)
# Autor: Alexandre V. Palaoro
# Licenciado sob a GNU GPL v3.0 ou posterior. Veja o arquivo LICENSE.

"""
Painel do medidor de temperatura e umidade (DHT22 · Orange Pi 3 LTS).

Páginas: Agora · Semana · Mês · Personalizado
Rodar com:  streamlit run painel.py

De onde vêm os dados:
- Se houver um endereço de banco na nuvem (em .streamlit/secrets.toml,
  seção [banco], chave url), lê do PostgreSQL (Supabase). É o caso do
  painel publicado no Streamlit Cloud.
- Se não houver, lê do arquivo dados.db local (SQLite). É o caso do
  painel rodando no próprio Orange Pi.
"""

import os
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# =====================================================================
# Configurações
# =====================================================================
CAMINHO_BD = Path(__file__).parent / "dados.db"
FUSO = ZoneInfo("America/Sao_Paulo")
UTC = ZoneInfo("UTC")
GRANDEZAS = ["temperatura", "umidade"]

# Visual: uma cor para cada grandeza (laranja = calor, azul = água)
COR = {"temperatura": "#FF8A4C", "umidade": "#38BDF8"}
UNIDADE = {"temperatura": "°C", "umidade": "%"}
NOME = {"temperatura": "Temperatura", "umidade": "Umidade relativa"}
FAIXA_MEDIDOR = {"temperatura": (0, 40), "umidade": (0, 100)}

FUNDO_CARTAO = "#141A26"
BORDA = "#232B3A"
TEXTO = "#E6EAF2"
TEXTO_SUAVE = "#8A94A7"
FONTE = "Source Sans Pro, Source Sans 3, sans-serif"

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

st.set_page_config(
    page_title="Medidor · temperatura e umidade",
    page_icon=":material/thermostat:",
    layout="wide",
)

CSS = f"""
<style>
.block-container {{ padding-top: 4.5rem; max-width: 1400px; }}
h1.titulo {{ font-size: 2rem; font-weight: 600; margin: 0; padding: 0; color: {TEXTO}; }}
.subtitulo {{ color: {TEXTO_SUAVE}; font-size: 0.95rem; margin: 0.15rem 0 1.4rem 0; }}
.cartao {{ background: {FUNDO_CARTAO}; border: 1px solid {BORDA}; border-radius: 14px;
          padding: 16px 18px; height: 100%; }}
.cartao .rotulo {{ color: {TEXTO_SUAVE}; font-size: 0.82rem; letter-spacing: 0.03em;
                  text-transform: uppercase; margin-bottom: 6px; }}
.cartao .valor {{ color: {TEXTO}; font-size: 1.65rem; font-weight: 600; line-height: 1.15; }}
.cartao .detalhe {{ color: {TEXTO_SUAVE}; font-size: 0.85rem; margin-top: 4px; }}
.grade {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 4px 0 8px 0; }}
.grade .cartao {{ padding: 12px 14px; }}
.grade .cartao .valor {{ font-size: 1.3rem; }}
.secao {{ display: flex; align-items: center; gap: 10px; font-size: 1.1rem; font-weight: 600;
         color: {TEXTO}; margin: 2px 0 8px 2px; }}
.ponto {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
.valor-atual {{ text-align: center; color: {TEXTO}; font-weight: 600; line-height: 1;
                font-size: clamp(1.6rem, 2.4vw, 2.6rem); margin: -0.6rem 0 0.6rem 0; }}
.valor-atual span {{ font-size: 0.55em; color: {TEXTO_SUAVE}; font-weight: 400; margin-left: 0.25em; }}
.status-ok {{ color: #4ADE80; }}
.status-erro {{ color: #F87171; }}
.rodape {{ margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid {BORDA};
           color: {TEXTO_SUAVE}; font-size: 0.85rem; line-height: 1.5; text-align: center; }}
@media (max-width: 700px) {{ .grade {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
</style>
"""


# =====================================================================
# Acesso aos dados
# =====================================================================
def url_nuvem():
    """Endereço do banco na nuvem, se configurado; senão None."""
    try:
        return st.secrets["banco"]["url"]
    except Exception:            # sem secrets.toml: usa o banco local
        return os.environ.get("BANCO_NUVEM_URL")


NA_NUVEM = url_nuvem() is not None
# Na nuvem os dados chegam em lotes a cada 5 min, então o atraso normal é maior
LIMITE_ATRASO_MIN = 12 if NA_NUVEM else 5


def iso_utc(momento):
    """Converte um datetime com fuso para o texto UTC usado no SQLite."""
    return momento.astimezone(UTC).isoformat(timespec="seconds")


def para_local(coluna):
    """Converte uma coluna de textos UTC em horários de Brasília (sem fuso)."""
    return pd.to_datetime(coluna, utc=True).dt.tz_convert(FUSO).dt.tz_localize(None)


class ErroBanco(Exception):
    """Falha de conexão com o banco na nuvem."""


def aviso_banco():
    st.error("Não foi possível conectar ao banco de dados. Tente novamente em alguns minutos.",
             icon=":material/cloud_off:")


def consultar(sql, params=()):
    """Roda uma consulta (escrita com '?') no banco certo e devolve uma tabela pandas.
    Datas nos parâmetros devem ser datetimes com fuso."""
    if NA_NUVEM:
        import psycopg   # só é necessário quando o painel lê da nuvem
        try:
            with psycopg.connect(url_nuvem(), connect_timeout=15, prepare_threshold=None) as con:
                with con.cursor() as cur:
                    cur.execute(sql.replace("?", "%s"), params)
                    colunas = [c.name for c in cur.description]
                    return pd.DataFrame(cur.fetchall(), columns=colunas)
        except psycopg.OperationalError as erro:
            print(f"Erro de conexão com o banco: {erro}", flush=True)   # detalhes só no log
            raise ErroBanco() from None
    params = tuple(iso_utc(p) if isinstance(p, datetime) else p for p in params)
    con = sqlite3.connect(CAMINHO_BD)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


@st.cache_data(ttl=60)
def carregar(inicio, fim):
    """Leituras válidas entre inicio e fim (horário local), em formato largo:
    índice = momento, colunas = temperatura e umidade."""
    df = consultar(
        "SELECT momento_utc, grandeza, valor FROM leituras "
        "WHERE momento_utc >= ? AND momento_utc < ? AND valor IS NOT NULL",
        (inicio, fim),
    )
    if df.empty:
        return pd.DataFrame(columns=GRANDEZAS, index=pd.DatetimeIndex([], name="momento"))
    df["momento"] = para_local(df["momento_utc"])
    largo = df.pivot_table(index="momento", columns="grandeza", values="valor")
    return largo.reindex(columns=GRANDEZAS).sort_index()


@st.cache_data(ttl=300)
def limites():
    """Primeiro e último momento com dados (horário local)."""
    df = consultar("SELECT MIN(momento_utc) AS ini, MAX(momento_utc) AS fim "
                   "FROM leituras WHERE valor IS NOT NULL")
    if df.empty or df.loc[0, "ini"] is None:
        return None, None
    return para_local(df["ini"]).iloc[0], para_local(df["fim"]).iloc[0]


@st.cache_data(ttl=20)
def ultima_leitura():
    """Última leitura válida: (momento local, {grandeza: valor})."""
    df = consultar(
        "SELECT momento_utc, grandeza, valor FROM leituras WHERE momento_utc = "
        "(SELECT MAX(momento_utc) FROM leituras WHERE valor IS NOT NULL) AND valor IS NOT NULL"
    )
    if df.empty:
        return None, {}
    return para_local(df["momento_utc"]).iloc[0], dict(zip(df["grandeza"], df["valor"]))


@st.cache_data(ttl=60)
def qualidade(inicio, fim):
    """Número de leituras e de falhas no intervalo (contando só a temperatura)."""
    df = consultar(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN valor IS NULL THEN 1 ELSE 0 END) AS falhas "
        "FROM leituras WHERE grandeza = 'temperatura' AND momento_utc >= ? AND momento_utc < ?",
        (inicio, fim),
    )
    return int(df.loc[0, "total"] or 0), int(df.loc[0, "falhas"] or 0)


# =====================================================================
# Componentes visuais
# =====================================================================
def cabecalho(titulo, subtitulo):
    st.markdown(f'<h1 class="titulo">{titulo}</h1><p class="subtitulo">{subtitulo}</p>',
                unsafe_allow_html=True)


def cartao(rotulo, valor, detalhe="", cor=TEXTO):
    return (f'<div class="cartao"><div class="rotulo">{rotulo}</div>'
            f'<div class="valor" style="color:{cor}">{valor}</div>'
            f'<div class="detalhe">{detalhe}</div></div>')


def fmt(numero, casas=1):
    """Número com vírgula decimal."""
    return f"{numero:.{casas}f}".replace(".", ",")


def titulo_secao(grandeza):
    st.markdown(f'<div class="secao"><span class="ponto" style="background:{COR[grandeza]}"></span>'
                f'{NOME[grandeza]}</div>', unsafe_allow_html=True)


def estatisticas(serie, grandeza):
    """Linha de cartões: média, desvio padrão, mínimo e máximo."""
    u = UNIDADE[grandeza]
    s = serie.dropna()
    dp = s.std() if len(s) > 1 else 0.0
    momento_min = s.idxmin().strftime("%d/%m %H:%M")
    momento_max = s.idxmax().strftime("%d/%m %H:%M")
    st.markdown(
        '<div class="grade">'
        + cartao("Média", f"{fmt(s.mean())} {u}", f"n = {len(s)} leituras", COR[grandeza])
        + cartao("Desvio padrão", f"{fmt(dp, 2)} {u}", "dispersão no período")
        + cartao("Mínimo", f"{fmt(s.min())} {u}", momento_min)
        + cartao("Máximo", f"{fmt(s.max())} {u}", momento_max)
        + "</div>",
        unsafe_allow_html=True,
    )


def layout_base(fig, altura):
    fig.update_layout(
        height=altura,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONTE, color=TEXTO_SUAVE, size=13),
        showlegend=False,
        separators=",.",   # vírgula decimal
        hoverlabel=dict(bgcolor="#1C2433", bordercolor=BORDA, font=dict(family=FONTE, color=TEXTO)),
    )
    return fig


def medidor(valor, grandeza):
    """Arco do mostrador (sem número; o número vai em HTML logo abaixo, ver valor_atual)."""
    fig = go.Figure(go.Indicator(
        mode="gauge",
        value=valor,
        gauge=dict(
            axis=dict(range=FAIXA_MEDIDOR[grandeza], tickcolor=BORDA,
                      tickfont=dict(color=TEXTO_SUAVE, size=12)),
            bar=dict(color=COR[grandeza], thickness=0.3),
            bgcolor="#1C2433",
            borderwidth=0,
        ),
    ))
    return layout_base(fig, 190).update_layout(margin=dict(l=30, r=30, t=20, b=14))


def valor_atual(valor, grandeza):
    """Número grande sob o arco; o tamanho acompanha a largura da janela."""
    st.markdown(
        f'<div class="valor-atual">{fmt(valor)}<span>{UNIDADE[grandeza]}</span></div>',
        unsafe_allow_html=True,
    )


def grafico(serie, grandeza, formato_x, reamostrar=None):
    """Linha da série, com a média (pontilhada) e a faixa média ± 1 desvio padrão."""
    s = serie.dropna()
    media = s.mean()
    dp = s.std() if len(s) > 1 else 0.0
    plot = s.resample(reamostrar).mean() if reamostrar else s   # médias por intervalo em períodos longos
    cor = COR[grandeza]
    r, g, b = (int(cor[i:i + 2], 16) for i in (1, 3, 5))

    fig = go.Figure()
    fig.add_hrect(y0=media - dp, y1=media + dp, fillcolor=f"rgba({r},{g},{b},0.08)", line_width=0)
    fig.add_hline(y=media, line=dict(color=cor, width=1, dash="dot"), opacity=0.8)
    fig.add_trace(go.Scatter(
        x=plot.index, y=plot.values, mode="lines", connectgaps=False,
        line=dict(color=cor, width=2.2),
        fill="tozeroy", fillcolor=f"rgba({r},{g},{b},0.06)",
        hovertemplate=f"%{{x|%d/%m %H:%M}}<br><b>%{{y:.1f}} {UNIDADE[grandeza]}</b><extra></extra>",
    ))

    # eixo Y ajustado aos dados e à faixa de ± 1 DP
    baixo = min(plot.min(), media - dp)
    alto = max(plot.max(), media + dp)
    folga = max((alto - baixo) * 0.12, 0.3)
    fig.update_yaxes(range=[baixo - folga, alto + folga], gridcolor="#1E2633", zeroline=False,
                     ticksuffix=f" {UNIDADE[grandeza]}")
    fig.update_xaxes(tickformat=formato_x, gridcolor="#1E2633", showline=False)
    return layout_base(fig, 300)


def secao_periodo(largo, formato_x, nome_arquivo, reamostrar=None):
    """Bloco padrão de todas as páginas: estatísticas + gráfico para cada grandeza, e o CSV."""
    if largo.dropna(how="all").empty:
        st.info("Não há leituras neste período.", icon=":material/info:")
        return

    for grandeza in GRANDEZAS:
        with st.container(border=True):
            titulo_secao(grandeza)
            estatisticas(largo[grandeza], grandeza)
            st.plotly_chart(grafico(largo[grandeza], grandeza, formato_x, reamostrar),
                            width="stretch", config={"displayModeBar": False})

    if reamostrar:
        st.caption(f"Gráficos com médias a cada {reamostrar.replace('min', ' min').replace('h', ' h')}; "
                   "estatísticas e CSV usam todas as leituras. Faixa sombreada = média ± 1 desvio padrão.")
    else:
        st.caption("Faixa sombreada = média ± 1 desvio padrão. Linha pontilhada = média.")

    tabela = largo.reset_index().rename(columns={
        "momento": "momento_local", "temperatura": "temperatura_C", "umidade": "umidade_pct"})
    st.download_button(
        "Baixar estes dados (CSV)",
        tabela.to_csv(index=False, date_format="%Y-%m-%d %H:%M:%S").encode("utf-8"),
        file_name=nome_arquivo,
        mime="text/csv",
        icon=":material/download:",
        type="primary",
    )


def sem_dados():
    st.info("Ainda não há leituras no banco de dados.", icon=":material/info:")


# =====================================================================
# Página 1: Agora
# =====================================================================
@st.fragment(run_every="60s")   # atualiza sozinha a cada minuto
def conteudo_agora():
    try:
        _conteudo_agora()
    except ErroBanco:
        aviso_banco()


def _conteudo_agora():
    momento, valores = ultima_leitura()
    if momento is None:
        sem_dados()
        return

    agora = datetime.now(FUSO).replace(tzinfo=None)
    atraso_min = (agora - momento).total_seconds() / 60
    origem = "dados enviados à nuvem a cada 5 min" if NA_NUVEM else "atualiza a cada minuto"
    cabecalho("Agora", f"Última leitura em {momento:%d/%m/%Y às %H:%M} · {origem}")

    if atraso_min > LIMITE_ATRASO_MIN:
        st.error(f"A última leitura foi há {int(atraso_min)} minutos: o coletor pode estar parado.",
                 icon=":material/warning:")

    fim = datetime.now(FUSO)
    inicio = fim - timedelta(hours=1)
    total, falhas = qualidade(inicio, fim)

    c1, c2, c3 = st.columns([1.2, 1.2, 1])
    for coluna, grandeza in ((c1, "temperatura"), (c2, "umidade")):
        with coluna, st.container(border=True):
            titulo_secao(grandeza)
            if grandeza in valores:
                st.plotly_chart(medidor(valores[grandeza], grandeza),
                                width="stretch", config={"displayModeBar": False})
                valor_atual(valores[grandeza], grandeza)
    with c3:
        estado = ('<span class="status-ok">● Coletando</span>' if atraso_min <= LIMITE_ATRASO_MIN
                  else '<span class="status-erro">● Parado</span>')
        st.markdown(cartao("Coletor", estado, f"última leitura há {max(int(atraso_min), 0)} min"),
                    unsafe_allow_html=True)
        st.write("")
        st.markdown(cartao("Última hora", f"{total - falhas} leituras",
                           f"{falhas} falha(s) de {total} tentativas"), unsafe_allow_html=True)

    st.write("")
    st.markdown('<p class="subtitulo" style="margin-bottom:0.6rem">Variação na última hora</p>',
                unsafe_allow_html=True)
    secao_periodo(carregar(inicio, fim), "%H:%M", f"medidor_ultima_hora_{fim:%Y%m%d_%H%M}.csv")


def pagina_agora():
    conteudo_agora()


# =====================================================================
# Página 2: Semana (segunda 00:00 até a segunda seguinte)
# =====================================================================
def rotulo_semana(segunda):
    domingo = segunda + timedelta(days=6)
    numero = (segunda.day - 1) // 7 + 1   # 1ª, 2ª... segunda-feira do mês
    return (f"{numero}ª semana de {MESES[segunda.month - 1]}/{segunda.year} · "
            f"seg {segunda:%d/%m} a dom {domingo:%d/%m}")


def pagina_semana():
    primeiro, ultimo = limites()
    if primeiro is None:
        sem_dados()
        return
    seg_inicial = primeiro.date() - timedelta(days=primeiro.weekday())
    seg_final = ultimo.date() - timedelta(days=ultimo.weekday())
    semanas = []
    s = seg_final
    while s >= seg_inicial:          # da mais recente para a mais antiga
        semanas.append(s)
        s -= timedelta(days=7)

    cabecalho("Semana", "De segunda a segunda, com médias a cada 15 minutos nos gráficos")
    segunda = st.selectbox("Escolha a semana", semanas, format_func=rotulo_semana)

    inicio = datetime.combine(segunda, time(0), tzinfo=FUSO)
    fim = inicio + timedelta(days=7)
    secao_periodo(carregar(inicio, fim), "%d/%m<br>%H:%M",
                  f"medidor_semana_{segunda:%Y%m%d}.csv", reamostrar="15min")


# =====================================================================
# Página 3: Mês
# =====================================================================
def pagina_mes():
    primeiro, ultimo = limites()
    if primeiro is None:
        sem_dados()
        return
    meses_disponiveis = pd.period_range(primeiro, ultimo, freq="M")
    anos = sorted({p.year for p in meses_disponiveis}, reverse=True)

    cabecalho("Mês", "Mês inteiro, com médias por hora nos gráficos")
    c1, c2, _ = st.columns([1, 1, 2])
    ano = c1.selectbox("Ano", anos)
    meses_do_ano = sorted((p.month for p in meses_disponiveis if p.year == ano), reverse=True)
    mes = c2.selectbox("Mês", meses_do_ano, format_func=lambda m: MESES[m - 1].capitalize())

    inicio = datetime(ano, mes, 1, tzinfo=FUSO)
    fim = datetime(ano + (mes == 12), mes % 12 + 1, 1, tzinfo=FUSO)
    secao_periodo(carregar(inicio, fim), "%d/%m",
                  f"medidor_{ano}_{mes:02d}.csv", reamostrar="1h")


# =====================================================================
# Página 4: Personalizado (um dia, ou uma hora específica)
# =====================================================================
def pagina_personalizada():
    primeiro, ultimo = limites()
    if primeiro is None:
        sem_dados()
        return

    cabecalho("Personalizado", "Escolha um dia e, se quiser, uma hora específica")
    c1, c2, _ = st.columns([1, 1, 2])
    dia = c1.date_input("Data", value=ultimo.date(), min_value=primeiro.date(),
                        max_value=ultimo.date(), format="YYYY/MM/DD")
    hora = c2.time_input("Hora (deixe vazio para o dia todo)", value=None, step=3600)

    if hora is None:
        inicio = datetime.combine(dia, time(0), tzinfo=FUSO)
        fim = inicio + timedelta(days=1)
        st.markdown(f'<p class="subtitulo">Dia todo · {dia:%d/%m/%Y}</p>', unsafe_allow_html=True)
        nome = f"medidor_{dia:%Y%m%d}.csv"
    else:
        inicio = datetime.combine(dia, time(hora.hour), tzinfo=FUSO)
        fim = inicio + timedelta(hours=1)
        st.markdown(f'<p class="subtitulo">{dia:%d/%m/%Y} · das {inicio:%H:%M} às {fim:%H:%M}</p>',
                    unsafe_allow_html=True)
        nome = f"medidor_{dia:%Y%m%d}_{hora.hour:02d}h.csv"

    secao_periodo(carregar(inicio, fim), "%H:%M", nome)


# =====================================================================
# Navegação
# =====================================================================
st.markdown(CSS, unsafe_allow_html=True)
navegacao = st.navigation(
    [
        st.Page(pagina_agora, title="Agora", icon=":material/sensors:", default=True),
        st.Page(pagina_semana, title="Semana", icon=":material/date_range:", url_path="semana"),
        st.Page(pagina_mes, title="Mês", icon=":material/calendar_month:", url_path="mes"),
        st.Page(pagina_personalizada, title="Personalizado", icon=":material/tune:", url_path="personalizado"),
    ],
    position="top",
)
try:
    navegacao.run()
except ErroBanco:
    aviso_banco()

st.markdown(
    '<div class="rodape">Desenvolvido por Alexandre V. Palaoro como parte do projeto '
    'nº 407090/2025-8, financiado pelo CNPq, intitulado “Os caminhos para a diversificação '
    'morfológica dos quelípodos de <i>Aegla</i>: uma abordagem biomecânica”.</div>',
    unsafe_allow_html=True,
)
