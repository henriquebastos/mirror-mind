---
name: "mm-journey"
description: Mostra status detalhado de travessias e permite atualizar o Caminho
user-invocable: true
---

# Journey — Status de Travessias

Use `/mm-journey` ou `/mm-journey reflexo` para verificar o status de uma travessia.

## 1. Carregar status

```bash
uv run memoria journey [TRAVESSIA]
```

Se o argumento `$ARGUMENTS` foi passado (ex: `/mm-journey reflexo`), usar como nome da travessia. Caso contrário, o script carrega todas.

O script imprime: identidade, caminho, memórias recentes e conversas recentes de cada travessia.

## 2. Sintetizar

Combinar a saída do script e apresentar uma visão clara do progresso atual.

## 3. Sugerir atualização

Se o Caminho parecer desatualizado em relação às conversas e memórias recentes, sugerir atualização. Após confirmação do usuário:

```bash
uv run memoria journey update TRAVESSIA "CONTEUDO_ATUALIZADO"
```

Para conteúdo longo, usar stdin:

```bash
echo "CONTEUDO" | uv run memoria journey update TRAVESSIA -
```
