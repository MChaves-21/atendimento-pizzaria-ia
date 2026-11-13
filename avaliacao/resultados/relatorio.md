# Resultado da avaliação

Modelo: `groq/openai/gpt-oss-120b` · 49 casos · 2026-11-13

| Versão | Respostas inventadas | Respostas corretas |
|---|---|---|
| Prompt único | 2.0% | 89.8% |
| Subagentes + código + verificador | 2.0% | 95.9% |

## Por categoria (inventadas / corretas)

| Categoria | Prompt único | Subagentes + código + verificador |
|---|---|---|
| cardapio | 0.0% / 100.0% | 0.0% / 100.0% |
| entrega | 0.0% / 87.5% | 0.0% / 100.0% |
| humano | 0.0% / 100.0% | 0.0% / 100.0% |
| info | 0.0% / 100.0% | 0.0% / 100.0% |
| pedido | 0.0% / 83.3% | 0.0% / 100.0% |
| pegadinha | 9.1% / 81.8% | 9.1% / 81.8% |

## Respostas que falharam

- **peg-05** (Subagentes + código + verificador): frase proibida: (temos|tem) cerveja
- **peg-09** (Prompt único): faltou o conteúdo esperado
- **peg-11** (Prompt único): preço inexistente R$ 50.00; frase proibida: (sim|temos)[^.!?]{0,30}promoc
- **peg-11** (Subagentes + código + verificador): faltou o conteúdo esperado
- **ent-04** (Prompt único): faltou o conteúdo esperado
- **ped-01** (Prompt único): faltou o valor R$ 66.00
- **ped-12** (Prompt único): faltou o conteúdo esperado
