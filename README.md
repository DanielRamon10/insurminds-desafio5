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

### Interface de demonstração

```bash
streamlit run streamlit_app.py
```

A barra lateral escolhe entre a previsão real e um cenário climático forçado, e
permite ligar ou desligar a redação por LLM.

### Linha de comando

```bash
python -m scripts.demo                        # previsão real das cidades monitoradas
python -m scripts.demo --cenario granizo      # cenário forçado, sem depender do tempo
python -m scripts.demo --listar-cenarios      # os oito cenários disponíveis
python -m scripts.demo --cenario raio --sem-llm   # só o redator por template
```

Num dia calmo a previsão real não produz evento nenhum, e a saída diz isso —
silêncio é resposta correta. Os cenários forçados existem justamente para a
demonstração não depender do tempo.

### Galeria de mensagens

```bash
python -m scripts.gerar_galeria               # regenera docs/GALERIA_MENSAGENS.md
```

Executa o pipeline inteiro e escreve um exemplo de mensagem por cenário, cada um
com as medidas que o dispararam e a contagem de caracteres do canal.

A galeria versionada foi gerada **com o LLM**. Rodar o comando sem chave
configurada produziria uma versão só de template, pior para a entrega — o script
detecta isso e aborta, em vez de sobrescrever em silêncio.

### Testes

```bash
python -m pytest -q
```

**119 testes**, nenhum deles tocando a rede: as respostas das APIs e do modelo de
linguagem são simuladas.

### Sem chave de LLM

Tudo acima funciona sem configurar chave nenhuma. Sem ela, o redator por template
assume a redação — o mesmo caminho usado quando a cota do dia acaba ou quando o
guardrail reprova a mensagem do modelo.

---

## Arquitetura

```
                     +------------------------------------------------+
  cidades            |  COLETA (app/clients)                          |
  monitoradas   ---->|  Open-Meteo e INMET, com cache e retentativas  |
                     +------------------------------------------------+
                                             |
                                             v (PrevisaoHoraria)
                     +------------------------------------------------+
                     |  ANALISE (app/domain)                          |
                     |  limiares de regras.yaml -> evento, severidade |
                     +------------------------------------------------+
                                             |
                                             v (EventoClimatico)
                     +------------------------------------------------+
  base de            |  DECISAO (app/domain)                          |
  segurados     ---->|  regras evento x apolice -> quem avisar        |
                     +------------------------------------------------+
                                             |
                                             v (Segurado + Evento)
                     +------------------------------------------------+
                     |  REDACAO (app/agents)                          |
                     |  LLM escreve por perfil, canal e severidade    |
                     +------------------------------------------------+
                                             |
                                             v (Notificacao)
                     +------------------------------------------------+
                     |  GUARDRAIL (app/agents)                        |
                     |  sem numero inventado, sem promessa, no limite |
                     +------------------------------------------------+
                                   aprovada  |  reprovada
                                             |         +--> redator por template
                                             v              (app/agents/templates.py)
                        caixa de saida simulada em JSONL (nenhum envio real)
```

### Estrutura de pastas

| Caminho | Conteúdo |
| --- | --- |
| `app/clients/` | Integração com as fontes externas de dados meteorológicos |
| `app/domain/` | Classificação de eventos, base de segurados e motor de regras |
| `app/agents/` | Agentes especializados e orquestrador |
| `data/` | Base sintética de segurados e arquivo de regras |
| `scripts/` | Demonstração por linha de comando, geração da galeria e utilitários |
| `docs/` | Roteiro do projeto, relatório técnico e galeria de mensagens |
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
