# Intelligent Tool for Proactive Policyholder Communication

**Challenge 5 — InsurMinds Course · Instituto de Inteligência Artificial Aplicada (I2A2)**

*[Leia em português](README.pt-BR.md)*

A prototype (MVP) that monitors weather conditions, identifies risk events, decides which
policyholders should be warned and drafts the preventive message — before the claim
happens.

Licensed under the **MIT license** (see [LICENSE](LICENSE)).

---

## Team

| Member | Workstream |
| --- | --- |
| Daniel Ramon | A — Weather data collection |
| Paulo Henrique | B — Policyholders and business rules |
| Nicole Paes | C — Agents and message generation |
| Paulo Roberto | D — Delivery simulation and demo |
| Juliana Catarina | E — Documentation and submission (representative) |

---

## Covered scenarios

Two policy types and four weather events, giving seven active combinations:

| Event | Home | Auto | Signal in the API |
| --- | --- | --- | --- |
| Heavy rain | flooding, water ingress | aquaplaning, flooded road | `precipitation` |
| Lightning | electrical surge | not applicable | `weather_code` 95 + `cape` |
| Strong wind | roof tiles, loose objects | tree falling on the vehicle | `wind_gusts_10m` |
| Hail | roof, skylights, glass | bodywork and windshield | `cape` + `freezing_level_height` |

> Lightning × auto is deliberately dropped: a car is a Faraday cage, and there is no
> honest preventive recommendation to give in that case.

---

## Installation

Requires **Python 3.10 or newer**.

```bash
git clone https://github.com/DanielRamon10/insurminds-desafio5.git
cd insurminds-desafio5

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # Linux / macOS

pip install -r requirements.txt
```

### API key configuration

The weather data source (Open-Meteo) **requires no key**. A key is only needed for the
language model that drafts the messages.

```bash
copy .env.example .env           # Windows
# cp .env.example .env             # Linux / macOS
```

Open `.env` and fill in the key for your chosen provider. The default is Google Gemini,
which has a free tier — create a key at <https://aistudio.google.com/apikey>.

```env
LLM_PROVIDER=google
LLM_MODEL=gemini-3.6-flash
GOOGLE_API_KEY=your-key-here
```

The `.env` file is listed in `.gitignore` and **must never be committed**. No credential
appears anywhere in the source code.

---

## Running

### Demo interface

```bash
streamlit run streamlit_app.py
```

The sidebar switches between the real forecast and a forced weather scenario, and lets
you turn LLM drafting on or off.

### Command line

```bash
python -m scripts.demo                        # real forecast for the monitored cities
python -m scripts.demo --cenario granizo      # forced scenario, independent of the weather
python -m scripts.demo --listar-cenarios      # the eight available scenarios
python -m scripts.demo --cenario raio --sem-llm   # template drafter only
```

On a calm day the real forecast produces no event at all, and the output says so —
silence is a correct answer. The forced scenarios exist precisely so the demo doesn't
depend on the weather.

### Message gallery

```bash
python -m scripts.gerar_galeria               # regenerates docs/GALERIA_MENSAGENS.md
```

Runs the whole pipeline and writes one example message per scenario, each with the
measurements that triggered it and the character count for the channel.

The committed gallery was generated **with the LLM**. Running the command without a key
configured would produce a template-only version, worse for the submission — the script
detects this and aborts rather than overwriting silently.

> The messages in the gallery are in Portuguese: they are the product's output, addressed
> to Brazilian policyholders.

### Tests

```bash
python -m pytest -q
```

**119 tests**, none of them touching the network: the API and language-model responses
are stubbed.

### Without an LLM key

Everything above works with no key configured at all. Without one, the template drafter
takes over the writing — the same path used when the daily quota runs out or when the
guardrail rejects the model's message.

---

## Architecture

```
                     +------------------------------------------------+
  monitored          |  COLLECTION (app/clients)                      |
  cities        ---->|  Open-Meteo and INMET, with cache and retries  |
                     +------------------------------------------------+
                                             |
                                             v (PrevisaoHoraria)
                     +------------------------------------------------+
                     |  ANALYSIS (app/domain)                         |
                     |  regras.yaml thresholds -> event, severity     |
                     +------------------------------------------------+
                                             |
                                             v (EventoClimatico)
                     +------------------------------------------------+
  policyholder       |  DECISION (app/domain)                         |
  base          ---->|  event x policy rules -> who to warn           |
                     +------------------------------------------------+
                                             |
                                             v (Segurado + Evento)
                     +------------------------------------------------+
                     |  DRAFTING (app/agents)                         |
                     |  LLM writes per profile, channel and severity  |
                     +------------------------------------------------+
                                             |
                                             v (Notificacao)
                     +------------------------------------------------+
                     |  GUARDRAIL (app/agents)                        |
                     |  no invented figure, no promise, within limit  |
                     +------------------------------------------------+
                                   approved  |  rejected
                                             |         +--> template drafter
                                             v              (app/agents/templates.py)
                          simulated outbox in JSONL (nothing is actually sent)
```

### Repository layout

| Path | Contents |
| --- | --- |
| `app/clients/` | Integration with the external weather data sources |
| `app/domain/` | Event classification, policyholder base and the rules engine |
| `app/agents/` | Specialised agents and the orchestrator |
| `data/` | Synthetic policyholder base and the rules file |
| `scripts/` | Command-line demo, gallery generation and utilities |
| `docs/` | Project roadmap, technical report and message gallery |
| `tests/` | Automated tests |

---

## Data sources

Two public sources, complementary in nature, neither requiring a key.

### Numerical forecast — [Open-Meteo](https://open-meteo.com)

The primary source: it supplies the numbers the classifier interprets against the
thresholds set by the domain expert. Variables consumed: `precipitation`,
`wind_gusts_10m`, `weather_code` (WMO codes), `cape` (convective available potential
energy) and `freezing_level_height` (altitude of the 0 °C isotherm, used to estimate hail
risk).

### Official warnings — [INMET](https://portal.inmet.gov.br)

The complementary source: Brazil's National Institute of Meteorology has already decided
there is a risk and published the warning, with risks and instructions written by a
public authority. Matching to cities is done by **IBGE code**, never by name.

Its role is enrichment, not validation: a single warning can cover thousands of
municipalities, so it asserts something about the *region*, not about the city's
coordinates. The absence of an official warning never cancels a classified event, and its
presence never creates one.

---

## Notes

No notification is actually sent. SMS, email and *push* delivery is simulated and logged,
as the challenge brief specifies.
