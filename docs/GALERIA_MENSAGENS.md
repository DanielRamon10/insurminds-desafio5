# Galeria de mensagens por cenário

Tarefa **E.4**. Cada mensagem abaixo saiu do pipeline real — cenário
climático forçado, classificado pelos limiares de `data/regras.yaml`,
cruzado com a base de segurados e redigido pelos agentes. Nenhuma foi
escrita à mão.

Gerada em 30/08/2026 às 18:52 por `python -m scripts.gerar_galeria`.

---

## 1. Os sete cenários ativos

A matriz de negócio cobre sete pares evento × apólice. `raio × automotiva`
fica de fora por decisão do corretor: o veículo age como gaiola de Faraday
e não há recomendação preventiva honesta a fazer.

### Chuva intensa · alerta · apólice residencial

**Disparado por:** chuva na hora mais forte 35 mm/h; chuva acumulada em 24 h 81 mm

> Alerta de chuva intensa em Curitiba (35.0mm/h). Mantenha ralos desobstruídos e, se a água ameaçar entrar, proteja seus bens e desligue a energia local.

`SMS` · 151/160 caracteres · agente redator (LLM)

### Chuva intensa · alerta · apólice automotiva

**Disparado por:** chuva na hora mais forte 35 mm/h; chuva acumulada em 24 h 81 mm

> Bruno, alerta em Curitiba: previstos 35.0 mm/h (total de 81.0 mm). Evite áreas alagáveis e não atravesse ruas com água. Deixe o veículo em local alto e seguro agora.

`PUSH` · 165/240 caracteres · agente redator (LLM)

### Raio · alerta · apólice residencial

**Disparado por:** energia da tempestade (CAPE) 2200 J/kg; código de trovoada (WMO) 95

> Carla, alerta de raios em Curitiba! Para a segurança do seu lar e família, desconecte os aparelhos eletrônicos da tomada e evite usar a rede elétrica durante a tempestade. Mantenha-se em local protegido.

`PUSH` · 203/240 caracteres · agente redator (LLM)

### Vento forte · alerta · apólice residencial

**Disparado por:** rajada máxima 92 km/h

> Diego, alerta em Curitiba: rajadas de 92.0 km/h. Para proteger sua família, recolha objetos soltos, feche portas e janelas e afaste-se de árvores.

`SMS` · 146/160 caracteres · agente redator (LLM)

### Vento forte · alerta · apólice automotiva

**Disparado por:** rajada máxima 92 km/h

> Elisa, alerta de vento forte em Curitiba com rajadas de 92.0 km/h. Estacione seu carro em local coberto e seguro. Durante as rajadas, evite estacionar perto de árvores, placas, postes ou estruturas instáveis.

`PUSH` · 208/240 caracteres · agente redator (LLM)

### Granizo · alerta · apólice residencial

**Disparado por:** energia da tempestade (CAPE) 2800 J/kg; altura onde congela 2600 m

> Hugo, identificamos um alerta meteorológico com risco de granizo para a sua residência em Curitiba/PR. Os dados da região apontam CAPE de 2800.0 J/kg e nível de congelamento a 2600.0 metros, o que indica uma alta probabilidade de tempestade severa.

A sua segurança, a de sua família e a proteção do seu lar são a nossa maior prioridade. Para garantir que todos fiquem bem e seguros, pedimos que siga estas orientações preventivas o quanto antes:

- Recolha objetos que possam ser danificados em áreas descobertas.
- Evite permanecer sob claraboias, telhas translúcidas ou vidros amplos.
- Mantenha-se afastado de janelas durante a queda de granizo.

Por favor, permaneça em um local coberto e protegido. Nossos canais continuam à disposição para oferecer o suporte necessário para o cuidado com a sua casa.

`EMAIL` · 807/2000 caracteres · agente redator (LLM)

### Granizo · alerta · apólice automotiva

**Disparado por:** energia da tempestade (CAPE) 2800 J/kg; altura onde congela 2600 m

> Alerta de granizo em Curitiba, Iara! Recolha seu veículo para um local coberto nas próximas horas e evite dirigir durante a tempestade. Mantenha seu carro protegido e fique em segurança.

`PUSH` · 186/240 caracteres · agente redator (LLM)

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

> Bruno, alerta de chuva intensa em Curitiba (até 81.0mm). Evite trafegar por áreas alagáveis e não atravesse ruas com água acumulada. Se possível, estacione seu veículo em um local alto e seguro imediatamente.

`PUSH` · 208/240 caracteres · agente redator (LLM)

---

## 3. Mesmo evento, canais diferentes

O limite do canal muda o que cabe. O SMS corta em fronteira de palavra; o
e-mail acomoda a orientação inteira, separada em blocos.

### Canal SMS (limite 160)

**Disparado por:** energia da tempestade (CAPE) 2800 J/kg; altura onde congela 2600 m

> Iara, alerta de granizo em Curitiba. Recolha seu veículo para local coberto nas próximas horas e evite dirigir durante a tempestade.

`SMS` · 132/160 caracteres · agente redator (LLM)

### Canal PUSH (limite 240)

**Disparado por:** energia da tempestade (CAPE) 2800 J/kg; altura onde congela 2600 m

> Iara, alerta de granizo para Curitiba/PR! Recolha o veículo para local coberto nas próximas horas e evite dirigir durante a tempestade de granizo.

`PUSH` · 146/240 caracteres · agente redator (LLM)

### Canal EMAIL (limite 2000)

**Disparado por:** energia da tempestade (CAPE) 2800 J/kg; altura onde congela 2600 m

> Atenção, Iara. Existe um alerta de tempestade de granizo para a região de Curitiba/PR nas próximas horas. Os dados de monitoramento indicam condições severas na atmosfera, com CAPE em 2800.0 J/kg e nível de congelamento em 2600.0 metros.

Para proteger o seu veículo e garantir sua segurança, tome as seguintes providências imediatas:

- Recolha o veículo para um local coberto (garagem fechada, estacionamento subterrâneo ou coberto) nas próximas horas.
- Evite dirigir durante a tempestade de granizo.
- Se a tempestade começar enquanto você estiver no trânsito, procure o abrigo coberto mais próximo e seguro para estacionar. Não pare embaixo de árvores, estruturas frágeis ou fiação elétrica.
- Mantenha-se em abrigo seguro até a tempestade passar completamente.

Adote essas medidas preventivas o quanto antes.

`EMAIL` · 815/2000 caracteres · agente redator (LLM)

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

> Elisa, há previsão de vento forte com rajadas de 65 km/h em Curitiba. Estacione em local coberto e seguro. Evite parar perto de árvores, postes, placas ou estruturas instáveis para proteger seu veículo.

`PUSH` · 202/240 caracteres · agente redator (LLM)

### Vento forte · severidade alerta

**Disparado por:** rajada máxima 92 km/h

> Elisa, alerta de vento forte com rajadas de 92 km/h em Curitiba. Estacione seu veículo em local coberto e seguro. Durante as rajadas, evite parar perto de árvores, postes, placas ou outras estruturas instáveis.

`PUSH` · 210/240 caracteres · agente redator (LLM)

---

## Como reproduzir

```
python -m scripts.gerar_galeria            # com LLM, se houver chave no .env
python -m scripts.gerar_galeria --sem-llm  # só o redator por template
```
