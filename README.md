# Ferramenta Inteligente para Comunicação Proativa com o Segurado

**Desafio 5 — Curso InsurMinds · Instituto de Inteligência Artificial Aplicada (I2A2)**

Protótipo (MVP) que monitora condições meteorológicas, identifica eventos de
risco, decide quais segurados devem ser avisados e gera a comunicação
preventiva — antes que o sinistro aconteça.

Licenciado sob a **licença MIT** (ver [LICENSE](LICENSE)).

---

## Grupo

| Integrante | Frente |
| --- | --- |
| Daniel Ramon | A — Coleta meteorológica |
| Paulo Henrique | B — Segurados e regras de negócio |
| Nicole Paes | C — Agentes e geração de mensagens |
| Paulo Roberto | D — Simulação de envio e demonstração |
| Juliana Catarina | E — Documentação e entrega (representante) |

---

## Cenários cobertos

Duas apólices e quatro eventos climáticos, com sete combinações ativas:

| Evento | Residencial | Automotiva | Sinal na API |
| --- | --- | --- | --- |
| Chuva intensa | alagamento, infiltração | aquaplanagem, via alagada | `precipitation` |
| Raio | surto elétrico | não se aplica | `weather_code` 95 + `cape` |
| Vento forte | telhas, objetos soltos | queda de árvore sobre o veículo | `wind_gusts_10m` |
| Granizo | telhado, claraboias, vidros | lataria e para-brisa | `cape` + `freezing_level_height` |

> Raio × automotiva é intencionalmente descartado: um automóvel é uma gaiola de
> Faraday e não há recomendação preventiva honesta a dar nesse caso.

---

## Instalação

Requer **Python 3.10 ou superior**.

```bash
git clone https://github.com/DanielRamon10/insurminds-desafio5.git
cd insurminds-desafio5

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # Linux / macOS

pip install -r requirements.txt
```

### Configuração da chave de API

A fonte de dados meteorológicos (Open-Meteo) **não exige chave**. A chave é
necessária apenas para o modelo de linguagem que redige as mensagens.

```bash
copy .env.example .env           # Windows
# cp .env.example .env             # Linux / macOS
```

Abra o `.env` e preencha a chave do provedor escolhido. O padrão é o Google
Gemini, que possui camada gratuita — crie a chave em
<https://aistudio.google.com/apikey>.

```env
LLM_PROVIDER=google
LLM_MODEL=gemini-3.6-flash
GOOGLE_API_KEY=sua-chave-aqui
```

O arquivo `.env` está no `.gitignore` e **nunca deve ser versionado**. Nenhuma
credencial aparece no código-fonte.

---

## Execução

```bash
streamlit run streamlit_app.py     # interface de demonstração
python scripts/demo.py             # fluxo completo por linha de comando
python -m pytest tests/ -v         # testes dos contratos de dados
```

> Em construção. Consulte o roteiro do projeto em [`docs/`](docs/) para o estado
> atual de cada frente de trabalho.

---

## Arquitetura

```
                     +--------------------------------------------+
  cidades            |  COLETA (app/clients)                      |
  monitoradas   ---->|  consulta a API meteorologica e normaliza  |
                     +----------------------+---------------------+
                                            |
                                            v
                     +--------------------------------------------+
                     |  ANALISE (app/domain)                      |
                     |  chuva, raio, vento forte e granizo        |
                     +----------------------+---------------------+
                                            |
                                            v
                     +--------------------------------------------+
  base de            |  DECISAO (app/domain)                      |
  segurados     ---->|  regras evento x apolice -> quem avisar    |
                     +----------------------+---------------------+
                                            |
                                            v
                     +--------------------------------------------+
                     |  REDACAO (app/agents)                      |
                     |  LLM escreve a mensagem por perfil e canal |
                     +----------------------+---------------------+
                                            |
                                            v
                        caixa de saida simulada (nenhum envio real)
```

### Estrutura de pastas

| Caminho | Conteúdo |
| --- | --- |
| `app/clients/` | Integração com as fontes externas de dados meteorológicos |
| `app/domain/` | Classificação de eventos, base de segurados e motor de regras |
| `app/agents/` | Agentes especializados e orquestrador |
| `data/` | Base sintética de segurados e arquivo de regras |
| `scripts/` | Utilitários de demonstração e empacotamento |
| `docs/` | Roteiro do projeto e relatório técnico |
| `tests/` | Testes automatizados |

---

## Fonte de dados

Duas fontes públicas, de naturezas complementares e nenhuma exigindo chave.

### Previsão numérica — [Open-Meteo](https://open-meteo.com)

Fonte primária: entrega os números que o classificador interpreta com os
limiares definidos pelo especialista. Variáveis consumidas: `precipitation`,
`wind_gusts_10m`, `weather_code` (códigos WMO), `cape` (energia potencial
convectiva disponível) e `freezing_level_height` (altitude da isoterma de 0 °C,
usada para estimar risco de granizo).

### Avisos oficiais — [INMET](https://portal.inmet.gov.br)

Fonte complementar: o Instituto Nacional de Meteorologia já decidiu que há risco
e publicou o aviso, com riscos e instruções redigidos por órgão público. O
casamento com as cidades é por **código IBGE**, nunca por nome.

O papel é de enriquecimento, não de validação: um único aviso pode cobrir
milhares de municípios, então ele afirma algo sobre a *região*, não sobre a
coordenada da cidade. A ausência de aviso oficial nunca derruba um evento
classificado, e a presença dele nunca cria um.

---

## Observações

Nenhuma notificação é efetivamente enviada. O envio de SMS, e-mail ou *push* é
simulado e registrado, conforme previsto no enunciado do desafio.
