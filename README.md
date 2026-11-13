# 🍕 Atendente de IA para pizzaria: prompt único x subagentes

[![Testes](https://github.com/MChaves-21/atendimento-pizzaria-ia/actions/workflows/testes.yml/badge.svg)](https://github.com/MChaves-21/atendimento-pizzaria-ia/actions/workflows/testes.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-8E75B2?logo=googlegemini&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-Llama_3.1-F55036)

Um assistente de IA que **inventa** preço, sabor ou bairro de entrega faz a empresa perder dinheiro e o cliente perder a confiança. Este projeto compara duas formas de montar o mesmo atendente e **mede** quantas respostas inventadas cada uma produz:

1. **Prompt único:** todos os dados e todas as regras num só texto, e o modelo responde e faz as contas sozinho. É o jeito mais comum de começar.
2. **Subagentes:** um roteador classifica a mensagem e um subagente por fase atende, com um prompt curto e só os dados daquela fase. Preços, taxas e totais são calculados **em código**, e um **verificador** barra qualquer preço que não exista antes de a resposta chegar ao cliente.

> A "Pizzaria Bella Massa", o cardápio, os preços e os bairros são **fictícios**. É um projeto pessoal de estudo, sobre uma técnica pública de engenharia de IA.

## 🧭 Arquitetura

```mermaid
flowchart LR
    C([Cliente]) --> R{Roteador<br/>só classifica}
    R -->|info| I[Subagente Info<br/>horário, pagamento]
    R -->|cardápio| K[Subagente Cardápio<br/>só o cardápio]
    R -->|pedido| P[Subagente Pedido<br/>IA só extrai os itens]
    R -->|entrega| E[Subagente Entrega<br/>IA só extrai o bairro]
    R -->|humano| H[Chama a equipe]
    P --> CALC[[Cálculo em código<br/>preço, meio a meio, borda, taxa]]
    E --> CALC
    I --> V{{Verificador<br/>preço existe?}}
    K --> V
    V -->|inventou| RE[Gera de novo com aviso<br/>ou usa resposta segura]
    V -->|ok| C
    CALC --> C
    RE --> C
```

**Por que funciona melhor:**

- **Menos contexto, mais foco:** o subagente de cardápio nem conhece os bairros; o de entrega nem conhece os sabores. Há menos coisas para o modelo confundir.
- **Conta é com o código:** a IA transforma "uma G meio calabresa meio carne de sol e uma coca" em JSON. Validar o sabor, cobrar o mais caro no meio a meio e somar a taxa é Python (`atendente/pedido.py`).
- **Verificação antes de responder:** o `verificador.py` confere cada preço citado. Se algum não existir, o subagente gera de novo, avisando qual foi o erro. Se errar outra vez, responde com o texto seguro.

## 📊 Avaliação

O arquivo `avaliacao/casos.jsonl` tem **49 casos**: perguntas de cardápio, entrega, pedidos com conta para fechar e **pegadinhas** (pizza de pepperoni, bairro fora da área, tamanho GG, promoção que não existe). As duas versões respondem às mesmas conversas, e a nota é dada **por regras, sem IA julgando IA**:

- **Inventou:** citou preço que não existe, disse que tem um sabor que não tem ou bateu numa frase proibida do caso.
- **Correta:** não inventou e trouxe o que o caso exige (o total certo, a negativa, o horário).

```bash
cp .env.example .env              # coloque sua chave (Gemini ou Groq, ambos gratuitos)
export $(cat .env | xargs)
python -m avaliacao.avaliar       # gera avaliacao/resultados/: relatorio.md, grafico.png, respostas.csv
```

### Resultados

_Ainda não rodei a avaliação com um modelo real. Quando rodar, o `relatorio.md` e o gráfico gerados entram aqui, com o modelo e a data._

## 💬 Conversar pelo terminal

```bash
pip install -r requirements.txt
python -m atendente                 # subagentes
python -m atendente --monolitico    # prompt único, para comparar
```

```
Você: quero uma G meio calabresa meio carne de sol e uma coca lata
Atendente [pedido]: Anotado! Seu pedido até agora:
- 1x Pizza G meio Calabresa e meio Carne de Sol com Nata: R$ 74,00
- 1x Refrigerante lata 350 ml: R$ 6,00
Subtotal: R$ 80,00
Total: R$ 80,00
É para entrega (em qual bairro?) ou retirada no balcão?
```

## 🗂️ Estrutura

```
atendente/
  dados.py         # cardápio, taxas e horários (fonte única dos números)
  llm.py           # clientes Gemini e Groq + modelo simulado para testes
  roteador.py      # classifica a fase (com plano B por palavras-chave)
  subagentes.py    # info, cardápio, pedido, entrega, humano
  pedido.py        # validação e cálculo do pedido, 100% em código
  verificador.py   # barra preço e sabor inventados
  monolitico.py    # versão de comparação: prompt único
avaliacao/
  casos.jsonl      # 49 casos de teste
  avaliar.py       # roda as duas versões e gera o relatório
dados/pizzaria.json
tests/             # 50 testes com modelo simulado (rodam sem chave e sem internet)
```

## ✅ Testes

```bash
python -m pytest -q
```

Os testes usam um modelo **simulado**, então rodam no GitHub Actions sem chave de API. Eles cobrem o cálculo do pedido (meio a meio, borda, taxa, pedido mínimo), o verificador, o roteador com plano B, o reenvio quando a IA inventa um preço e a própria avaliação.

## 🛠️ Tecnologias

Python 3.12 · httpx · API do Gemini ou da Groq (Llama 3.1) · pytest · matplotlib · GitHub Actions
