"""Testes do parser de tasks de caminhos markdown."""

from memoria.tasks import parse_caminho_tasks, parse_done_tasks

TRAVESSIA = "reflexo"


class TestParseCaminhoTasks:
    def test_basic_checkbox_extracted(self):
        caminho = """
### Etapa 1: Início
- [ ] Tarefa simples
"""
        tasks = parse_caminho_tasks(caminho, TRAVESSIA)
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Tarefa simples"
        assert tasks[0]["status"] == "todo"
        assert tasks[0]["travessia"] == TRAVESSIA

    def test_stage_assigned_correctly(self):
        # The regex strips the "Etapa N:" prefix — only the label is captured
        caminho = """
### Etapa 2: Desenvolvimento
- [ ] Implementar feature
"""
        tasks = parse_caminho_tasks(caminho, TRAVESSIA)
        assert tasks[0]["stage"] == "Desenvolvimento"

    def test_multiple_tasks_under_same_stage(self):
        caminho = """
### Etapa 1: Planejamento
- [ ] Tarefa A
- [ ] Tarefa B
- [ ] Tarefa C
"""
        tasks = parse_caminho_tasks(caminho, TRAVESSIA)
        assert len(tasks) == 3
        assert all(t["stage"] == "Planejamento" for t in tasks)

    def test_tasks_under_different_stages(self):
        caminho = """
### Etapa 1: Início
- [ ] Alpha

### Etapa 2: Meio
- [ ] Beta
"""
        tasks = parse_caminho_tasks(caminho, TRAVESSIA)
        assert len(tasks) == 2
        assert tasks[0]["title"] == "Alpha"
        assert tasks[1]["title"] == "Beta"
        assert tasks[0]["stage"] != tasks[1]["stage"]

    def test_done_checkbox_ignored(self):
        caminho = """
### Etapa 1: Início
- [x] Já feito
- [ ] Pendente
"""
        tasks = parse_caminho_tasks(caminho, TRAVESSIA)
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Pendente"

    def test_completed_stage_skipped(self):
        caminho = """
### Etapa 1: Completa ✅
- [ ] Não deve ser extraída

### Etapa 2: Ativa
- [ ] Deve ser extraída
"""
        tasks = parse_caminho_tasks(caminho, TRAVESSIA)
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Deve ser extraída"

    def test_markdown_bold_stripped_from_title(self):
        caminho = """
### Etapa 1: Início
- [ ] **Título em negrito**
"""
        tasks = parse_caminho_tasks(caminho, TRAVESSIA)
        assert tasks[0]["title"] == "Título em negrito"

    def test_trailing_period_stripped(self):
        caminho = """
### Etapa 1: Início
- [ ] Tarefa com ponto final.
"""
        tasks = parse_caminho_tasks(caminho, TRAVESSIA)
        assert tasks[0]["title"] == "Tarefa com ponto final"

    def test_task_without_stage_not_extracted(self):
        """Tasks before any ### heading should not be extracted."""
        caminho = "- [ ] Tarefa sem etapa\n"
        tasks = parse_caminho_tasks(caminho, TRAVESSIA)
        assert len(tasks) == 0

    def test_empty_caminho(self):
        tasks = parse_caminho_tasks("", TRAVESSIA)
        assert tasks == []

    def test_no_tasks_in_caminho(self):
        caminho = """
### Etapa 1: Planejamento
Apenas texto descritivo, sem checkboxes.
"""
        tasks = parse_caminho_tasks(caminho, TRAVESSIA)
        assert tasks == []

    def test_indented_checkbox_extracted(self):
        caminho = """
### Etapa 1: Início
    - [ ] Task indentada
"""
        tasks = parse_caminho_tasks(caminho, TRAVESSIA)
        assert len(tasks) == 1

    def test_travessia_set_on_all_tasks(self):
        caminho = """
### Etapa 1
- [ ] Task A
- [ ] Task B
"""
        tasks = parse_caminho_tasks(caminho, "minha-travessia")
        assert all(t["travessia"] == "minha-travessia" for t in tasks)


class TestParseDoneTasks:
    def test_basic_done_checkbox_extracted(self):
        caminho = """
### Etapa 1: Concluída
- [x] Tarefa feita
"""
        tasks = parse_done_tasks(caminho, TRAVESSIA)
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Tarefa feita"
        assert tasks[0]["status"] == "done"

    def test_uppercase_X_matches(self):
        caminho = """
### Etapa 1
- [X] Feita com X maiúsculo
"""
        tasks = parse_done_tasks(caminho, TRAVESSIA)
        assert len(tasks) == 1

    def test_open_checkbox_ignored(self):
        caminho = """
### Etapa 1
- [ ] Pendente
- [x] Concluída
"""
        tasks = parse_done_tasks(caminho, TRAVESSIA)
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Concluída"

    def test_stage_assigned(self):
        # "Etapa N:" prefix is stripped by the regex
        caminho = """
### Etapa 3: Entrega
- [x] Deploy feito
"""
        tasks = parse_done_tasks(caminho, TRAVESSIA)
        assert tasks[0]["stage"] == "Entrega"

    def test_bold_stripped(self):
        caminho = """
### Etapa 1
- [x] **Concluída em negrito**
"""
        tasks = parse_done_tasks(caminho, TRAVESSIA)
        assert tasks[0]["title"] == "Concluída em negrito"

    def test_trailing_period_stripped(self):
        caminho = """
### Etapa 1
- [x] Feita com ponto.
"""
        tasks = parse_done_tasks(caminho, TRAVESSIA)
        assert tasks[0]["title"] == "Feita com ponto"

    def test_empty_returns_empty(self):
        assert parse_done_tasks("", TRAVESSIA) == []

    def test_both_parsers_together(self):
        """parse_caminho_tasks and parse_done_tasks should split correctly."""
        caminho = """
### Etapa 1: Sprint
- [x] Tarefa concluída
- [ ] Tarefa pendente
"""
        pending = parse_caminho_tasks(caminho, TRAVESSIA)
        done = parse_done_tasks(caminho, TRAVESSIA)
        assert len(pending) == 1
        assert len(done) == 1
        assert pending[0]["status"] == "todo"
        assert done[0]["status"] == "done"
