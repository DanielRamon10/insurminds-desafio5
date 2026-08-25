# Revisão da planilha da frente B

Registro do que foi recebido do especialista, do que foi corrigido e do que
ainda precisa de confirmação. Os limiares em si estão todos aproveitados —
nenhum número foi alterado.

**Recebido em:** 25/08/2026
**Origem:** `FRENTE_B_limiares_e_segurados_preenchido.xlsx`
**Resultado:** `data/regras.yaml`

---

## 1. Deslocamento de uma linha na tabela de limiares

Os valores foram preenchidos **uma linha acima** do lugar correspondente. A
primeira dupla de valores caiu na linha de cabeçalho, e cada dupla seguinte
ficou na linha do critério anterior.

O diagnóstico é inequívoco porque **as unidades casam perfeitamente** ao
deslocar tudo uma linha para baixo — "60 km/h" só pode ser rajada, "800 J/kg"
só pode ser CAPE. Nenhum valor foi inventado ou adivinhado: apenas
reposicionado.

### Como foi corrigido

| Critério | Unidade | Atenção | Alerta |
| --- | --- | --- | --- |
| Chuva acumulada em 24 h | mm | 40 | 60 |
| Chuva na hora mais forte | mm/h | 15 | 30 |
| Rajada máxima | km/h | 60 | 80 |
| CAPE (raio) | J/kg | 800 | 1.500 |
| CAPE (granizo) | J/kg | 1.500 | 2.500 |
| Altura de congelamento | m | abaixo de 3.800 | abaixo de 3.200 |

As justificativas acompanharam o mesmo deslocamento e foram realinhadas junto.
Cada uma está no campo `porque` do `regras.yaml`, pronta para o relatório.

### Duplicata resolvida

As duas últimas linhas preenchidas traziam o mesmo par de valores para a altura
de congelamento (3.800 / 3.200 m), com justificativas equivalentes. Mantida a
redação da última, que é a mais completa: *"...maior a chance de o granizo
alcançar o solo sem derreter. O indicador deve ser analisado junto com CAPE e
demais condições da tempestade."*

---

## 2. Pendente de confirmação: granizo + apólice residencial

A recomendação recebida para **granizo + residencial** trata de veículo:

> "Se possível, mantenha o veículo em garagem ou sob cobertura resistente e
> evite deixá-lo exposto ao tempo até o fim da tempestade."

Isso descreve a apólice **automotiva**, que já tem sua própria recomendação na
linha seguinte. As outras seis estão corretas e específicas.

Redação proposta para a residencial, marcada como `revisao_pendente: true` no
`regras.yaml` até o aval do especialista:

> "Recolha objetos que possam ser danificados em áreas descobertas, evite
> permanecer sob claraboias, telhas translúcidas ou vidros amplos e mantenha-se
> afastado de janelas durante a queda de granizo."

**Esta é a única pendência da frente B.** Uma frase confirmada ou reescrita
fecha a tarefa.

---

## 3. Ganho não previsto: os eventos compostos

As justificativas trouxeram uma informação que a planilha não pedia
explicitamente — e que melhora a regra:

- **Granizo:** *"O critério deve ser combinado com instabilidade (CAPE)"*
- **Raio:** CAPE indica *"ambiente favorável a tempestades"*, não a descarga em si

Ou seja, nem raio nem granizo devem ser decididos por um único número. O
`regras.yaml` reflete isso com o campo `combinacao`:

| Evento | Combinação | Significado |
| --- | --- | --- |
| Chuva intensa | `qualquer` | basta um critério atingir o limiar |
| Vento forte | `qualquer` | critério único |
| Raio | `todos` | trovoada confirmada **e** CAPE suficiente |
| Granizo | `todos` | CAPE alto **e** congelamento baixo |

Para o raio foi acrescentado o critério de **código WMO de trovoada** (95, 96 ou
99), que não estava na planilha porque é detalhe da fonte de dados, não de
seguro. Sem ele, CAPE alto sozinho classificaria como raio qualquer tarde de
verão instável.

---

## 4. Aba de segurados

Nenhum comentário registrado nas 45 linhas — a base foi aceita como está.

---

## Situação das tarefas da frente B

| Tarefa | Situação |
| --- | --- |
| B.1 Base de segurados | concluída — 45 segurados, base aceita sem ressalvas |
| B.2 Classificador de eventos | limiares definidos; falta implementar em código |
| B.3 Motor de regras | `data/regras.yaml` — alterável sem tocar em Python |
| B.4 Justificar cada limiar | concluída — seis justificativas, prontas para o relatório |
