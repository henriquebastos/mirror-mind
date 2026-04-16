# Dados Pessoais do Espelho — Template

Este diretório contém os templates para configurar o espelho para um novo usuário.

## Estrutura

```
users/me/
  self/           ← Identidade profunda (alma, propósito, configuração)
    soul.yaml       Quem o espelho é e como opera
    config.yaml     Modelo default, briefing curto
  ego/            ← Identidade operacional (comportamento do dia-a-dia)
    identity.yaml   O que o espelho faz, quem é o usuário
    behavior.yaml   Tom, estilo, regras de interação
  user/           ← Perfil do usuário
    identity.yaml   Perfil completo (história, família, personalidade)
    (disc.yaml)     Opcional: perfil DISC
    (big5.yaml)     Opcional: perfil Big Five
  organization/   ← Contexto organizacional
    identity.yaml   Relação com empresas/organizações
    principles.yaml Princípios profissionais
  personas/       ← Lentes especializadas
    _template.yaml  Template para criar personas
  travessias/     ← Jornadas de vida
    _template.yaml  Template para criar travessias
  conversas/      ← Conversas exportadas (criado automaticamente)
```

## Como usar

1. Copie este diretório para o local desejado:
   ```bash
   cp -r users/me ~/.config/espelho/seu-nome
   ```

2. Configure o `.env`:
   ```env
   MIRROR_USER_DIR=~/.config/espelho/seu-nome
   ```

3. Preencha os YAMLs com seus dados pessoais.

4. Crie personas copiando `personas/_template.yaml`.

5. Crie travessias copiando `travessias/_template.yaml`.

6. Execute o seed para popular o banco:
   ```bash
   uv run python -m memoria.seed --env production
   ```

## Dica

Quanto mais detalhado você for nos YAMLs, melhor o espelho te conhece.
Não tenha medo de escrever muito — o espelho precisa de contexto para
operar com profundidade.
