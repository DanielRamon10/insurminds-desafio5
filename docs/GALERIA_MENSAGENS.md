# Galeria de mensagens por cenário

Tarefa **E.4**. Cada mensagem abaixo saiu do pipeline real — cenário
climático forçado, classificado pelos limiares de `data/regras.yaml`,
cruzado com a base de segurados e redigido pelos agentes. Nenhuma foi
escrita à mão.

Gerada em 30/08/2026 às 16:54 por `python -m scripts.gerar_galeria --sem-llm`.

---

## 1. Os sete cenários ativos

A matriz de negócio cobre sete pares evento × apólice. `raio × automotiva`
fica de fora por decisão do corretor: o veículo age como gaiola de Faraday
e não há recomendação preventiva honesta a fazer.

### Chuva intensa · alerta · apólice residencial

**Disparado por:** chuva na hora mais forte 35 mm/h; chuva acumulada em 24 h 81 mm

> ALERTA: chuva intensa em Curitiba-PR. chuva na hora mais forte 35 mm/h, chuva acumulada [...] Evite áreas sujeitas a alagamento, mantenha ralos [...]

`SMS` · 149/160 caracteres · redator por template

### Chuva intensa · alerta · apólice automotiva

**Disparado por:** chuva na hora mais forte 35 mm/h; chuva acumulada em 24 h 81 mm

> ALERTA: chuva intensa em Curitiba-PR. chuva na hora mais forte 35 mm/h, chuva acumulada em 24 h 81 mm. Evite estacionar ou trafegar por áreas alagáveis; se possível, deixe o veículo em local alto e seguro e não atravesse ruas com [...]

`PUSH` · 235/240 caracteres · redator por template

### Raio · alerta · apólice residencial

**Disparado por:** energia da tempestade (CAPE) 2200 J/kg; código de trovoada (WMO) 95

> ALERTA: tempestade com raios em Curitiba-PR. energia convectiva de 2200 J/kg. Desconecte aparelhos eletrônicos sensíveis da tomada, evite usar equipamentos ligados à rede elétrica durante a tempestade e mantenha-se em local protegido.

`PUSH` · 234/240 caracteres · redator por template

### Vento forte · alerta · apólice residencial

**Disparado por:** rajada máxima 92 km/h

> ALERTA: vento forte em Curitiba-PR. rajadas de até 92 km/h. Recolha ou fixe objetos soltos em quintais e varandas, feche portas e janelas e afaste-se [...]

`SMS` · 155/160 caracteres · redator por template

### Vento forte · alerta · apólice automotiva

**Disparado por:** rajada máxima 92 km/h

> ALERTA: vento forte em Curitiba-PR. rajadas de até 92 km/h. Estacione em local coberto e seguro; durante rajadas fortes, evite estacionar perto de árvores, placas, postes ou outras estruturas instáveis.

`PUSH` · 202/240 caracteres · redator por template

### Granizo · alerta · apólice residencial

**Disparado por:** energia da tempestade (CAPE) 2800 J/kg; altura onde congela 2600 m

> ALERTA: Granizo previsto para Curitiba/PR (próximas 24 horas).

Medidas observadas: energia convectiva de 2800 J/kg, altitude de congelamento em 2600 m.

Orientação preventiva: Recolha objetos que possam ser danificados em áreas descobertas, evite permanecer sob claraboias, telhas translúcidas ou vidros amplos e mantenha-se afastado de janelas durante a queda de granizo.

`EMAIL` · 373/2000 caracteres · redator por template

### Granizo · alerta · apólice automotiva

**Disparado por:** energia da tempestade (CAPE) 2800 J/kg; altura onde congela 2600 m

> ALERTA: granizo em Curitiba-PR. energia convectiva de 2800 J/kg, altitude de congelamento em 2600 m. Recolha o veículo para local coberto nas próximas horas e evite dirigir durante a tempestade de granizo.

`PUSH` · 205/240 caracteres · redator por template

---

## 2. Mesma tempestade, apólices diferentes

O contraste que justifica cruzar evento com apólice: o mesmo evento, na
mesma cidade e na mesma hora, rende orientações opostas conforme o que o
segurado tem a proteger.

### Apólice residencial

**Disparado por:** chuva na hora mais forte 35 mm/h; chuva acumulada em 24 h 81 mm

> ALERTA: chuva intensa em Curitiba-PR. chuva na hora mais forte 35 mm/h, chuva acumulada em 24 h 81 mm. Evite áreas sujeitas a alagamento, mantenha ralos desobstruídos e, se houver risco de entrada de água, proteja objetos e [...]

`PUSH` · 229/240 caracteres · redator por template

### Apólice automotiva

**Disparado por:** chuva na hora mais forte 35 mm/h; chuva acumulada em 24 h 81 mm

> ALERTA: chuva intensa em Curitiba-PR. chuva na hora mais forte 35 mm/h, chuva acumulada em 24 h 81 mm. Evite estacionar ou trafegar por áreas alagáveis; se possível, deixe o veículo em local alto e seguro e não atravesse ruas com [...]

`PUSH` · 235/240 caracteres · redator por template

---

## 3. Mesmo evento, canais diferentes

O limite do canal muda o que cabe. O SMS corta em fronteira de palavra; o
e-mail acomoda a orientação inteira, separada em blocos.

### Canal SMS (limite 160)

**Disparado por:** energia da tempestade (CAPE) 2800 J/kg; altura onde congela 2600 m

> ALERTA: granizo em Curitiba-PR. energia convectiva de 2800 J/kg, altitude de [...] Recolha o veículo para local coberto nas próximas horas e evite [...]

`SMS` · 152/160 caracteres · redator por template

### Canal PUSH (limite 240)

**Disparado por:** energia da tempestade (CAPE) 2800 J/kg; altura onde congela 2600 m

> ALERTA: granizo em Curitiba-PR. energia convectiva de 2800 J/kg, altitude de congelamento em 2600 m. Recolha o veículo para local coberto nas próximas horas e evite dirigir durante a tempestade de granizo.

`PUSH` · 205/240 caracteres · redator por template

### Canal EMAIL (limite 2000)

**Disparado por:** energia da tempestade (CAPE) 2800 J/kg; altura onde congela 2600 m

> ALERTA: Granizo previsto para Curitiba/PR (próximas 24 horas).

Medidas observadas: energia convectiva de 2800 J/kg, altitude de congelamento em 2600 m.

Orientação preventiva: Recolha o veículo para local coberto nas próximas horas e evite dirigir durante a tempestade de granizo.

`EMAIL` · 281/2000 caracteres · redator por template

---

## 4. Atenção e alerta

As duas severidades existem para graduar a urgência sem duplicar as regras.
No redator por template a graduação aparece no rótulo de abertura e no número
citado — a orientação preventiva é a mesma, porque a do especialista não muda
com a intensidade. É o agente redator com LLM que ajusta também o tom: o
prompt pede *sem alarmismo* em atenção e *mais urgente, sem gerar pânico* em
alerta. Rodando esta galeria com uma chave configurada, a diferença entre os
dois blocos abaixo fica bem maior.

### Vento forte · severidade atenção

**Disparado por:** rajada máxima 65 km/h

> AVISO: vento forte em Curitiba-PR. rajadas de até 65 km/h. Estacione em local coberto e seguro; durante rajadas fortes, evite estacionar perto de árvores, placas, postes ou outras estruturas instáveis.

`PUSH` · 201/240 caracteres · redator por template

### Vento forte · severidade alerta

**Disparado por:** rajada máxima 92 km/h

> ALERTA: vento forte em Curitiba-PR. rajadas de até 92 km/h. Estacione em local coberto e seguro; durante rajadas fortes, evite estacionar perto de árvores, placas, postes ou outras estruturas instáveis.

`PUSH` · 202/240 caracteres · redator por template

---

## Como reproduzir

```
python -m scripts.gerar_galeria            # com LLM, se houver chave no .env
python -m scripts.gerar_galeria --sem-llm  # só o redator por template
```

> **Nota.** Esta edição saiu inteira pelo redator por template — o caminho
> determinístico da tarefa C.4, que assume quando não há chave de LLM
> configurada, quando a cota do dia acaba ou quando o guardrail reprova a
> mensagem do modelo. Rodando com uma chave no `.env`, o mesmo comando
> regenera esta galeria com as mensagens do agente redator.
