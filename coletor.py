#!/usr/bin/env python3
# Medidor: registrador contínuo de temperatura e umidade para laboratório
# Copyright (C) 2026 Universidade Federal do Paraná (UFPR)
# Autor: Alexandre V. Palaoro
# Licenciado sob a GNU GPL v3.0 ou posterior. Veja o arquivo LICENSE.

"""
Coletor de temperatura e umidade (DHT22) para o Orange Pi 3 LTS.
Lê o sensor a cada INTERVALO_S segundos e grava no banco SQLite.
"""

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------- Configurações ----------------
INTERVALO_S = 60                                    # segundos entre leituras
CAMINHO_BD = Path(__file__).parent / "dados.db"     # banco na mesma pasta do script
NOME_SENSOR = "dht22_ar"
PASTA_IIO = Path("/sys/bus/iio/devices")
MAX_TENTATIVAS = 5

ESQUEMA = """
CREATE TABLE IF NOT EXISTS leituras (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    momento_utc TEXT    NOT NULL,
    sensor      TEXT    NOT NULL,
    grandeza    TEXT    NOT NULL,
    valor       REAL,
    unidade     TEXT    NOT NULL,
    tentativas  INTEGER NOT NULL,
    enviado     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_leituras_momento ON leituras (momento_utc);
"""


# ---------------- Sensor ----------------
def encontrar_sensor():
    """Devolve a pasta do sensor DHT no sistema, ou None se não achar."""
    for dispositivo in PASTA_IIO.glob("iio:device*"):
        if "dht" in (dispositivo / "name").read_text():
            return dispositivo
    return None


def ler_dht22(sensor):
    """Devolve (temperatura, umidade, tentativas). Valores None se todas falharem."""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            temp = int((sensor / "in_temp_input").read_text()) / 1000
            umid = int((sensor / "in_humidityrelative_input").read_text()) / 1000
            # descarta valores fisicamente impossíveis para o DHT22
            if -40 <= temp <= 80 and 0 <= umid <= 100:
                return temp, umid, tentativa
        except OSError:
            pass                      # falha de comunicação: tenta de novo
        time.sleep(2.5)               # o DHT22 precisa de ~2 s entre medições
    return None, None, MAX_TENTATIVAS


# ---------------- Banco de dados ----------------
def abrir_banco(caminho):
    """Abre (ou cria) o banco e garante que a tabela existe."""
    con = sqlite3.connect(caminho)
    con.execute("PRAGMA journal_mode=WAL")   # permite ler o banco enquanto o coletor grava
    con.executescript(ESQUEMA)
    return con


def gravar(con, momento, temp, umid, tentativas):
    """Grava uma linha para temperatura e outra para umidade."""
    linhas = [
        (momento, NOME_SENSOR, "temperatura", temp, "°C", tentativas),
        (momento, NOME_SENSOR, "umidade",     umid, "%",  tentativas),
    ]
    with con:   # 'with' garante que as duas linhas sejam gravadas juntas (ou nenhuma)
        con.executemany(
            "INSERT INTO leituras (momento_utc, sensor, grandeza, valor, unidade, tentativas) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            linhas,
        )


# ---------------- Programa principal ----------------
def main():
    con = abrir_banco(CAMINHO_BD)
    print(f"Gravando em {CAMINHO_BD} a cada {INTERVALO_S} s", flush=True)

    while True:
        inicio = time.monotonic()

        sensor = encontrar_sensor()
        if sensor is None:
            print("Sensor não encontrado; tento de novo no próximo ciclo.", flush=True)
            temp, umid, tentativas = None, None, 0
        else:
            temp, umid, tentativas = ler_dht22(sensor)

        momento = datetime.now(timezone.utc).isoformat(timespec="seconds")
        gravar(con, momento, temp, umid, tentativas)
        print(f"{momento}  T={temp}  UR={umid}  tentativas={tentativas}", flush=True)

        # espera o que falta para completar o intervalo
        tempo_gasto = time.monotonic() - inicio
        time.sleep(max(0, INTERVALO_S - tempo_gasto))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nEncerrado pelo usuário.")
