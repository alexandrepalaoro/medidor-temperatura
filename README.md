# Medidor de temperatura e umidade

Registrador contínuo de temperatura e umidade do ar para laboratório, feito com um
Orange Pi 3 LTS e um sensor DHT22 (AM2302). As leituras são gravadas a cada minuto
num banco SQLite local, enviadas a cada 5 minutos para um banco PostgreSQL na nuvem
(Supabase) e exibidas num painel web em Streamlit.

## Como funciona

```
DHT22 ──► coletor.py ──► dados.db (SQLite, no Orange Pi)
                              │
                         enviar.py (a cada 5 min)
                              ▼
                     PostgreSQL (Supabase) ──► painel.py (Streamlit Cloud)
```

Sem internet, as leituras continuam sendo gravadas localmente e sobem quando a
conexão volta.

## Hardware

| Sensor DHT22 | Orange Pi 3 LTS (conector de 26 pinos) |
|---|---|
| VCC (+) | pino 1 (3,3 V) |
| DATA (out) | pino 8 (PL2) |
| GND (−) | pino 6 (GND) |

O pino 1 fica na ponta do conector próxima à entrada USB-C de energia.
Use 3,3 V, não 5 V: os GPIOs do Orange Pi não toleram 5 V.

## Arquivos

| Arquivo | Função |
|---|---|
| `coletor.py` | Lê o sensor a cada minuto e grava no SQLite |
| `enviar.py` | Envia ao PostgreSQL as leituras ainda não enviadas |
| `painel.py` | Painel web (páginas Agora, Semana, Mês, Personalizado) |
| `.streamlit/config.toml` | Tema visual do painel |
| `requirements.txt` | Pacotes Python do painel |
| `sistema/dht22.dts` | Overlay do device tree que ativa o driver `dht11` do kernel no pino PL2 |
| `sistema/*.service`, `*.timer` | Serviços do systemd no Orange Pi |

## Sistema

- Orange Pi 3 LTS com Armbian (Ubuntu 26.04, kernel 6.18 sunxi64)
- Leitura pelo driver `dht11` do kernel (IIO), ativado por `sistema/dht22.dts`
  (`sudo armbian-add-overlay sistema/dht22.dts`). O overlay também reduz o filtro
  de interrupção (`input-debounce`) do banco L para 1 µs, necessário para o DHT22.

## Segredos

O endereço do banco na nuvem fica fora do repositório:
- no Orange Pi, em `~/medidor/nuvem.env` (`BANCO_NUVEM_URL=...`);
- no Streamlit Cloud, em *Settings → Secrets* (`[banco]` / `url = "..."`).

Sem esse endereço, o painel lê o `dados.db` local.

## Licença, registro e financiamento

Copyright © 2026 Universidade Federal do Paraná (UFPR).
Autor: Alexandre Varaschin Palaoro.

Programa registrado no INPI (Certificado de Registro de Programa de Computador,
processo nº BR512026009241-8, publicado em 14/10/2026), tendo a UFPR como titular.
A versão registrada corresponde ao commit `2d7572a`.

Distribuído sob a licença GNU General Public License v3.0 (veja `LICENSE`):
você pode usar, estudar, modificar e redistribuir o programa, desde que as
versões derivadas também sejam distribuídas sob a GPL-3.0, com o código-fonte aberto.

Desenvolvido por Alexandre V. Palaoro como parte do projeto nº 407090/2025-8,
financiado pelo Conselho Nacional de Desenvolvimento Científico e Tecnológico (CNPq),
intitulado “Os caminhos para a diversificação morfológica dos quelípodos de *Aegla*:
uma abordagem biomecânica”.



