#!/usr/bin/env python3
"""
Envia para o banco na nuvem (PostgreSQL no Supabase) as leituras
que ainda não foram enviadas (coluna enviado = 0 no SQLite local).

É seguro rodar quantas vezes quiser: linhas que já estão na nuvem são
ignoradas (ON CONFLICT DO NOTHING). Se a internet cair, as linhas ficam
pendentes e vão na próxima execução.

O endereço do banco vem da variável de ambiente BANCO_NUVEM_URL
(definida no arquivo nuvem.env, que NUNCA deve ir para o GitHub).
"""

import os
import sqlite3
import sys
from pathlib import Path

import psycopg

CAMINHO_BD = Path(__file__).parent / "dados.db"
LOTE = 1000   # quantas linhas enviar por vez

SQL_INSERIR = (
    "INSERT INTO leituras (momento_utc, sensor, grandeza, valor, unidade, tentativas) "
    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING"
)


def main():
    url = os.environ.get("BANCO_NUVEM_URL")
    if not url:
        sys.exit("Variável BANCO_NUVEM_URL não definida (veja nuvem.env).")

    local = sqlite3.connect(CAMINHO_BD, timeout=30)
    total = 0

    # prepare_threshold=None evita problemas com o "pooler" de conexões do Supabase
    with psycopg.connect(url, connect_timeout=20, prepare_threshold=None) as nuvem:
        while True:
            linhas = local.execute(
                "SELECT id, momento_utc, sensor, grandeza, valor, unidade, tentativas "
                "FROM leituras WHERE enviado = 0 ORDER BY id LIMIT ?",
                (LOTE,),
            ).fetchall()
            if not linhas:
                break

            # 1) grava na nuvem e confirma
            with nuvem.cursor() as cur:
                cur.executemany(SQL_INSERIR, [linha[1:] for linha in linhas])
            nuvem.commit()

            # 2) só depois marca como enviadas no banco local
            with local:
                local.executemany("UPDATE leituras SET enviado = 1 WHERE id = ?",
                                  [(linha[0],) for linha in linhas])
            total += len(linhas)

    pendentes = local.execute("SELECT COUNT(*) FROM leituras WHERE enviado = 0").fetchone()[0]
    local.close()
    print(f"{total} linhas enviadas; {pendentes} pendentes.")


if __name__ == "__main__":
    main()
