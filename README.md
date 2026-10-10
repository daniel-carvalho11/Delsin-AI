# Delsin AI — Manual Técnico

> Assistente de IA pessoal, modular e local. Matriz para a geração de futuros agentes especialistas.

| Item | Valor |
|---|---|
| Versão | 0.1.0 (MVP) |
| Plataforma alvo | Linux Fedora 43, Wayland/X11 |
| Python | 3.14.x (testado em 3.14.7) |
| Repositório | https://github.com/daniel-carvalho11/Delsin-AI |
| Personalidade | Analítica, pragmática, prestativa, focada em eficiência técnica |

Convenção deste manual: **DEVE** = obrigatório; **NÃO DEVE** = proibido; **RECOMENDADO** = desvio só com justificativa registrada no commit.

---

## Sumário

1. [Requisitos](#1-requisitos)
2. [Instalação](#2-instalação)
3. [Execução](#3-execução)
4. [Uso da interface](#4-uso-da-interface)
5. [Arquitetura](#5-arquitetura)
6. [Contratos do Core](#6-contratos-do-core)
7. [Criando uma skill](#7-criando-uma-skill)
8. [Configuração](#8-configuração)
9. [Módulo de voz](#9-módulo-de-voz)
10. [Logs](#10-logs)
11. [Segurança](#11-segurança)
12. [Limitações e gargalos conhecidos](#12-limitações-e-gargalos-conhecidos)
13. [Solução de problemas](#13-solução-de-problemas)
14. [Fluxo de desenvolvimento e Git](#14-fluxo-de-desenvolvimento-e-git)
15. [Roadmap](#15-roadmap)

---

## 1. Requisitos

### 1.1 Sistema (Fedora)

| Pacote | Motivo |
|---|---|
| `python3-tkinter` | Base gráfica do customtkinter |
| `portaudio-devel` | Biblioteca nativa usada pelo PyAudio |
| `gcc`, `python3-devel` | Compilação do PyAudio pelo pip |
| `espeak-ng` | Síntese de voz (TTS) |
| PipeWire (padrão no Fedora) | Servidor de áudio; o microfone é aberto através dele |

```bash
sudo dnf install python3-tkinter portaudio-devel espeak-ng gcc python3-devel
```

### 1.2 Python (`requirements.txt`, versões fixas)

| Pacote | Versão |
|---|---|
| customtkinter | 6.0.0 |
| SpeechRecognition | 3.17.0 (puxa `audioop-lts` e `standard-aifc`, removidos da stdlib no 3.13) |
| PyAudio | 0.2.14 |

As versões **DEVEM** permanecer fixas. Atualizar uma dependência exige: alterar `requirements.txt`, rodar os testes e testar a GUI e a voz manualmente, tudo no mesmo commit.

### 1.3 Rede

- Texto, skills e TTS: **funcionam offline**.
- STT (voz → texto): **exige internet** no MVP (serviço Google). Ver [§12](#12-limitações-e-gargalos-conhecidos).

---

## 2. Instalação

```bash
# 1. Dependências do sistema
sudo dnf install python3-tkinter portaudio-devel espeak-ng gcc python3-devel

# 2. Código
mkdir -p ~/ProjetoIA && cd ~/ProjetoIA
git clone https://github.com/daniel-carvalho11/Delsin-AI.git delsin
cd delsin

# 3. Ambiente virtual (DEVE se chamar .venv e ficar na raiz do projeto)
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Verificação
python -m unittest discover -s tests -v   # 6 testes, todos OK
```

Regras do ambiente virtual:

- O venv **DEVE** ser `.venv/` na raiz do projeto. O VS Code o detecta automaticamente e o `.gitignore` o exclui.
- Um venv **NÃO DEVE** ser movido nem copiado: os scripts dele guardam caminhos absolutos. Mudou a pasta do projeto, apague `.venv/` e repita o passo 3.
- O venv **NÃO DEVE** ser versionado.

---

## 3. Execução

Sempre a partir da raiz do projeto, com o venv ativo (`source .venv/bin/activate`):

| Comando | Efeito |
|---|---|
| `python main.py` | Abre o painel |
| `DELSIN_DEBUG=1 python main.py` | Mesmo painel, com logs em nível DEBUG |
| `DELSIN_LANG=en-US python main.py` | Muda o idioma do reconhecimento de voz |
| `python -m unittest discover -s tests -v` | Testes do Core (sem GUI nem áudio) |

O `main.py` **DEVE** ser executado com a raiz do projeto como diretório atual, porque os imports são absolutos (`from core...`).

**Encerrar:** fechar a janela, `Ctrl+C` no terminal ou `kill <pid>` (SIGTERM). Os três caminhos fazem o mesmo desligamento ordenado: interrompem a fala, encerram os pools do Core e chamam `teardown()` das skills.

### 3.1 VS Code

```bash
code ~/ProjetoIA/delsin
```

Já versionado em `.vscode/`:

- `settings.json`: interpretador `.venv/bin/python` e testes `unittest` na aba *Testing*.
- `launch.json`: perfis **Delsin** e **Delsin (debug logs)**. Basta apertar `F5`.

Extensão necessária: *Python* (ms-python.python), que instala o *Python Debugger* junto.

---

## 4. Uso da interface

```
┌──────────────┬──────────────────────────────────────────────┐
│ DELSIN       │ Console                     10/10/2026 14:03 │
│              │ ┌──────────────────────────────────────────┐ │
│ MÓDULOS      │ │ Conversa (Você / Delsin / Sistema)       │ │
│ ● Núcleo     │ └──────────────────────────────────────────┘ │
│ ● Skills     │ LOG DE SISTEMA                               │
│ ● Microfone  │ ┌──────────────────────────────────────────┐ │
│ ● Voz        │ │ 14:03:01  INFO  Skill registrada: clock  │ │
│ ● IA / LLM   │ └──────────────────────────────────────────┘ │
│              │ [ Digite um comando… ] [🎙 Ouvir] [Enviar]   │
│ ◯ Responder  │                                              │
│   por voz    │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

### 4.1 Estados dos módulos

| Cor | Estado | Significado |
|---|---|---|
| Cinza | `offline` | Não configurado ou desligado |
| Âmbar | `iniciando` | Verificando dependências/dispositivos |
| Verde | `online` | Pronto |
| Roxo | `ativo` | Em operação (ex.: microfone ouvindo) |
| Vermelho | `erro` | Falhou; o motivo aparece abaixo do nome e no log |

Uma falha de voz **não** derruba o sistema: o Delsin continua em modo texto.

### 4.2 Atalhos

| Tecla | Ação |
|---|---|
| `Enter` | Envia o texto digitado |
| `Ctrl+Espaço` | Inicia uma escuta (igual ao botão *Ouvir*) |

### 4.3 Quando o Delsin fala

A resposta é falada se **todas** as condições forem verdadeiras:

1. O módulo **Voz (TTS)** está `online`;
2. A skill não marcou a resposta como `speak=False` (ex.: `help`);
3. O switch **Responder por voz** está ligado **ou** o comando veio pelo microfone.

Ao clicar em *Ouvir*, qualquer fala em andamento é interrompida (evita que o Delsin transcreva a própria voz).

### 4.4 Comandos disponíveis no MVP

| Skill | Palavras-gatilho (acentos ignorados) | Exemplo |
|---|---|---|
| `clock` | hora, horas, horário, data, que dia, hoje | "que horas são?", "que dia é hoje?" |
| `system_status` | status, diagnóstico, sistema, memória, cpu | "status do sistema" |
| `help` | ajuda, help, comandos, o que você faz, skills | "ajuda" |

Cada resposta exibe `ok|falha · skill · latência em ms`.

---

## 5. Arquitetura

### 5.1 Estrutura

```
delsin/
├── main.py              # Composition root: instancia e liga módulos, controla threads
├── requirements.txt
├── config/
│   ├── settings.py      # Settings imutáveis + caminhos XDG (pathlib)
│   └── persona.py       # Mensagens e system prompt do Delsin
├── core/
│   ├── contracts.py     # Request, Response, Skill, SkillContext, SkillInfo, Source
│   ├── agent.py         # Agent (execução) + Router (estratégia de escolha)
│   └── logger.py        # Arquivo rotativo + terminal + fila da GUI
├── skills/
│   ├── __init__.py      # discover_skills(): auto-descoberta de plugins
│   ├── _base.py         # KeywordSkill (base, não descoberta)
│   └── builtin.py       # clock, system_status, help
├── voice/
│   ├── stt.py           # SpeechToText (microfone → texto)
│   ├── tts.py           # TextToSpeech (texto → espeak-ng)
│   └── alsa.py          # Silencia o ruído da libasound no stderr
├── gui/
│   ├── dashboard.py     # Janela customtkinter
│   ├── events.py        # StatusEvent, MessageEvent, ModuleState
│   └── theme.py         # Paleta e fontes
└── tests/
    └── test_agent.py
```

### 5.2 Regras de dependência (obrigatórias)

```
            main.py  (único que importa todos)
         ┌─────┼──────────┬──────────┐
         ▼     ▼          ▼          ▼
       gui/  voice/    skills/ ──► core/ ──► config/
```

| Módulo | PODE importar | NÃO DEVE importar |
|---|---|---|
| `config/` | stdlib | qualquer outro módulo do projeto |
| `core/` | `config/`, stdlib | `gui/`, `voice/`, `skills/` |
| `skills/` | `core.contracts`, `skills._base`, stdlib | `gui/`, `voice/`, `core.agent` |
| `voice/` | `config/`, stdlib | `core/`, `gui/`, `skills/` |
| `gui/` | `core.logger` (só o tipo `LogItem`), stdlib, customtkinter | `core.agent`, `voice/`, `skills/` |
| `main.py` | tudo | — |

Violar esta tabela é motivo de rejeição do commit. É ela que permite extrair um agente especialista levando só `core/` + `config/` + as skills dele.

### 5.3 Fluxo de um comando

```
Entrada (texto ou voz)
  └─► DelsinApp.submit()           cria Request(text, source)
        └─► Agent.submit()         pool "delsin-dispatch" (2 threads)
              └─► Agent.handle()
                    ├─ vazio?             → Response(core, falha, sem fala)
                    ├─ > 2000 caracteres? → Response(core, falha)
                    ├─ Router.select()    → maior score ≥ 0.5
                    │     └─ nenhuma      → Response(fallback, falha)
                    └─ skill.handle()     pool "delsin-skill" (4 threads), timeout 10 s
                          ├─ timeout      → Response(falha); a thread segue até terminar
                          └─ exceção      → Response(falha); stack trace no log
              └─► callback → fila da GUI (+ fila do TTS, se aplicável)
```

### 5.4 Modelo de threads

| Thread | Responsabilidade | Pode tocar na GUI? |
|---|---|---|
| main | Loop do Tkinter; lê as filas a cada 50 ms | **Sim (única)** |
| `delsin-boot` | Descobre skills, inicializa TTS e STT | Não |
| `delsin-listen` | Captura do microfone + transcrição | Não |
| `delsin-dispatch-*` | Roteamento e espera pela skill | Não |
| `delsin-skill-*` | Execução de `Skill.handle()` | Não |
| `delsin-tts` | Fila de fala → subprocesso `espeak-ng` | Não |

**Regra absoluta:** nenhuma thread além da main **DEVE** chamar métodos de widgets. Comunicação com a GUI **DEVE** passar por `DelsinApp._post()` (fila `events`) ou pelo `logging` (fila de logs). O Tkinter não é thread-safe; violar isso causa travamentos intermitentes e difíceis de reproduzir.

Os dois pools do Agent são separados de propósito: se o dispatcher e as skills dividissem o mesmo pool, requisições simultâneas poderiam ocupar todas as threads esperando umas pelas outras (deadlock).

---

## 6. Contratos do Core

Definidos em `core/contracts.py`. São a **API pública** do projeto: mudanças **DEVEM** ser retrocompatíveis ou atualizar todas as skills no mesmo commit.

### 6.1 `Request` (imutável)

| Campo | Tipo | Padrão | Descrição |
|---|---|---|---|
| `text` | `str` | — | Texto bruto do usuário |
| `source` | `Source` | `TEXT` | `TEXT` ou `VOICE` |
| `id` | `str` | 8 hex aleatórios | Correlaciona as linhas de log |
| `created_at` | `datetime` | agora | Momento da criação |
| `normalized` | property | — | Minúsculas, espaços colapsados |

### 6.2 `Response` (imutável)

| Campo | Tipo | Padrão | Descrição |
|---|---|---|---|
| `text` | `str` | — | Resposta exibida/falada |
| `skill` | `str` | — | Nome da skill (ou `core`/`fallback`) |
| `success` | `bool` | `True` | `False` é exibido em vermelho |
| `speak` | `bool` | `True` | `False` impede a fala |
| `latency_ms` | `float` | `0.0` | **Preenchido pelo Agent**; a skill não deve definir |
| `data` | `dict` | `{}` | Dados estruturados para consumidores futuros |

### 6.3 `Skill` (classe abstrata)

| Membro | Obrigatório | Regra |
|---|---|---|
| `name` | Sim | Único, `snake_case`. Duplicatas são rejeitadas no registro |
| `description` | Sim | Uma frase; aparece no comando `ajuda` |
| `score(request) -> float` | Sim | Entre 0.0 e 1.0. **DEVE** ser rápido (< 1 ms), sem I/O nem rede: roda para todas as skills em todo comando |
| `handle(request, context) -> Response` | Sim | Pode ser lento (até `skill_timeout_s`). Exceções são capturadas pelo Core |
| `setup()` | Não | Adquire recursos no registro. Se lançar exceção, a skill não é registrada |
| `teardown()` | Não | Libera recursos no desligamento |

### 6.4 `SkillContext`

O que a skill enxerga do agente — **e nada além disso**:

| Campo | Descrição |
|---|---|
| `list_skills()` | Lista de `SkillInfo(name, description)` registradas |
| `persona_name` | Nome do assistente |

---

## 7. Criando uma skill

### 7.1 Passo a passo

1. Crie `skills/<nome>.py` (nome **sem** `_` no início; arquivos com `_` não são descobertos).
2. Defina uma classe concreta que herde de `KeywordSkill` (gatilho por palavras) ou de `Skill` (lógica própria em `score`).
3. Adicione testes em `tests/`.
4. Reinicie o Delsin. A skill aparece em *Skills* e no comando `ajuda`.

### 7.2 Exemplo

```python
# skills/uptime.py
from pathlib import Path

from core.contracts import Request, Response, SkillContext
from skills._base import KeywordSkill


class UptimeSkill(KeywordSkill):
    name = "uptime"
    description = "Informa há quanto tempo o computador está ligado."
    keywords = ("uptime", "ligado ha quanto tempo", "tempo ligado")

    def handle(self, request: Request, context: SkillContext) -> Response:
        seconds = float(Path("/proc/uptime").read_text().split()[0])
        hours, rest = divmod(int(seconds), 3600)
        return Response(f"Ligado há {hours} h {rest // 60} min.", self.name)
```

### 7.3 Regras obrigatórias para skills

- **DEVE** retornar sempre um `Response`; nunca `None`.
- **DEVE** usar `pathlib.Path` para qualquer caminho de arquivo.
- **DEVE** definir timeout explícito em toda chamada de rede ou subprocesso.
- **NÃO DEVE** acessar GUI, voz ou o `Agent` diretamente.
- **NÃO DEVE** usar `subprocess` com `shell=True` nem montar comandos com texto do usuário.
- **NÃO DEVE** guardar segredos no código. Use variáveis de ambiente lidas em `setup()`.
- **NÃO DEVE** fazer I/O em `score()`.
- Respostas longas ou em lista **DEVEM** usar `speak=False`.
- `KeywordSkill` retorna score fixo de **0.9**. Para prioridade maior, sobrescreva `score()`.

---

## 8. Configuração

### 8.1 `config/settings.py` — `CoreSettings`

| Campo | Padrão | Efeito |
|---|---|---|
| `skill_timeout_s` | 10.0 | Tempo máximo de `Skill.handle()` |
| `min_confidence` | 0.5 | Score mínimo para uma skill ser escolhida |
| `max_input_chars` | 2000 | Entradas maiores são rejeitadas |
| `skill_workers` | 4 | Threads do pool de skills |

### 8.2 `VoiceSettings`

| Campo | Padrão | Efeito |
|---|---|---|
| `language` | `pt-BR` | Idioma do STT |
| `preferred_input_devices` | `("pipewire", "default")` | Nomes exatos de dispositivo, em ordem de preferência |
| `ambient_calibration_s` | 0.5 | Calibração de ruído antes de cada escuta |
| `listen_timeout_s` | 5.0 | Espera máxima pelo início da fala |
| `phrase_time_limit_s` | 10.0 | Duração máxima de uma frase |
| `recognition_timeout_s` | 8.0 | Timeout da chamada de rede do STT |
| `tts_voice` | `pt-br` | Voz do espeak-ng (`espeak-ng --voices` lista as opções) |
| `tts_rate` | 170 | Palavras por minuto |
| `tts_timeout_s` | 30.0 | Tempo máximo de uma fala antes de matar o processo |
| `tts_queue_size` | 10 | Falas pendentes; excedentes são descartadas com aviso |

### 8.3 Variáveis de ambiente

| Variável | Efeito |
|---|---|
| `DELSIN_DEBUG=1` | Logs em nível DEBUG (inclui o score de roteamento) |
| `DELSIN_LANG` | Idioma do STT. **Não** altera a voz do TTS |
| `XDG_DATA_HOME` | Base dos dados (padrão `~/.local/share`) |
| `XDG_CACHE_HOME` | Base do cache (padrão `~/.cache`) |

### 8.4 Caminhos

| Caminho | Conteúdo | Permissão |
|---|---|---|
| `~/.local/share/delsin/` | Dados do usuário | `0700` |
| `~/.local/share/delsin/logs/` | Logs | `0700` |
| `~/.cache/delsin/` | Cache (reservado) | `0700` |

As pastas são criadas na inicialização (`ensure_dirs()`), e a permissão é reaplicada a cada execução.

### 8.5 Personalidade (`config/persona.py`)

Contém todas as mensagens fixas (saudação, fallback, erros) e o `system_prompt` que será enviado ao LLM quando integrado. Para criar um agente especialista, instancie outro `Persona` e passe ao `Agent`. **NÃO** espalhe texto de personalidade pelas skills.

---

## 9. Módulo de voz

### 9.1 STT (`voice/stt.py`)

1. No boot: valida SpeechRecognition e PyAudio, silencia o ALSA, lista dispositivos e escolhe o primeiro cujo nome seja **exatamente** `pipewire` ou `default`. Se nenhum existir, usa o padrão do PortAudio.
2. Em cada escuta: abre o microfone → calibra (0,5 s) → espera a fala (até 5 s) → grava (até 10 s) → **fecha o microfone** → envia para transcrição (até 8 s).
3. Só uma captura por vez. Um segundo pedido simultâneo retorna "Já existe uma captura em andamento".

Abrir dispositivos `hw:X,Y` diretamente **NÃO DEVE** ser feito: eles competem com o PipeWire pelo hardware e causam "Device unavailable" ou bloqueio.

Listar dispositivos:

```bash
python -c "import speech_recognition as sr; [print(i, n) for i, n in enumerate(sr.Microphone.list_microphone_names())]" 2>/dev/null
```

### 9.2 TTS (`voice/tts.py`)

- Cada fala é um subprocesso `espeak-ng -v <voz> -s <velocidade> --stdin`.
- O texto entra **por stdin**, nunca como argumento: não pode ser interpretado como opção ou comando.
- Fila única, consumida pela thread `delsin-tts`: falas nunca se sobrepõem.
- `stop()` esvazia a fila e encerra a fala atual (SIGTERM).
- O `pyttsx3` **NÃO DEVE** ser usado: o `runAndWait()` dele trava no Linux quando chamado por threads.

Teste isolado: `echo "teste de voz" | espeak-ng -v pt-br --stdin`

---

## 10. Logs

| Destino | Formato | Observação |
|---|---|---|
| `~/.local/share/delsin/logs/delsin.log` | completo, com data | Rotação a cada 1 MB, 3 backups |
| Terminal (stderr) | hora + nível + módulo | — |
| Painel *Log de sistema* | hora + nível | Mantém as últimas 1500 linhas; cores por nível |

Loggers: `delsin.app`, `delsin.core`, `delsin.skills`, `delsin.voice.stt`, `delsin.voice.tts`. Novos módulos **DEVEM** usar `logging.getLogger("delsin.<módulo>")`, nunca `print()`.

Acompanhar em tempo real: `tail -f ~/.local/share/delsin/logs/delsin.log`

---

## 11. Segurança

| # | Regra | Motivo |
|---|---|---|
| S1 | A pasta `skills/` **NÃO DEVE** ter permissão de escrita para outros usuários | Todo `.py` ali é executado no boot |
| S2 | Segredos (chaves de API) **DEVEM** ficar em `.env` ou no keyring do sistema | `.env` já está no `.gitignore` |
| S3 | Nenhuma skill **DEVE** executar comandos de shell montados com texto do usuário | Injeção de comandos |
| S4 | Todo texto vindo de voz ou de LLM **DEVE** ser tratado como não confiável | Injeção de prompt e comandos por áudio de terceiros (TV, vídeo, outra pessoa) |
| S5 | Skills com efeito colateral (arquivos, rede, sistema) **DEVEM** pedir confirmação explícita na GUI | Uma transcrição errada não pode virar uma ação destrutiva |
| S6 | Quando um LLM for integrado, as skills que ele puder acionar **DEVEM** estar numa lista de permissões | Limita o raio de dano de uma resposta maliciosa |
| S7 | O repositório **DEVE** permanecer privado enquanto houver intenção comercial | Proteção do código |

**Privacidade:** no MVP, o áudio de cada comando de voz é enviado ao Google para transcrição. Não fale dados sensíveis até o STT local ser implementado.

---

## 12. Limitações e gargalos conhecidos

| Item | Impacto | Mitigação planejada |
|---|---|---|
| STT na nuvem (Google) | +1 a 3 s por comando; exige internet; envia áudio para terceiros | `faster-whisper` ou Vosk local |
| Calibração por escuta | +0,5 s por comando | Calibrar uma vez e recalibrar periodicamente |
| Timeout de skill não mata a thread | Uma skill travada continua consumindo uma das 4 threads | Skills pesadas em subprocesso |
| Empate de score | Vence a skill registrada primeiro (ex.: "status do sistema hoje") | Router por LLM ou por pesos |
| Gatilho por palavra-chave | Não entende paráfrases | Router por LLM |
| Voz do espeak-ng | Robótica | Piper (TTS neural local), mesma interface |
| Skills só carregam no boot | Nova skill exige reiniciar | Hot-reload (futuro) |
| Sem wake word | Escuta só por botão/atalho | openWakeWord / Porcupine |
| GUI via XWayland | Escala em HiDPI pode variar | `ctk.set_widget_scaling()` |

---

## 13. Solução de problemas

| Sintoma | Causa provável | Ação |
|---|---|---|
| `ModuleNotFoundError: No module named 'customtkinter'` | venv não ativado | `source .venv/bin/activate` |
| `No module named '_tkinter'` | Falta `python3-tkinter` | `sudo dnf install python3-tkinter` |
| `pip install PyAudio` falha com `portaudio.h` | Falta `portaudio-devel` | `sudo dnf install portaudio-devel gcc python3-devel` |
| `ModuleNotFoundError: No module named 'core'` | Executado fora da raiz | `cd ~/ProjetoIA/delsin` antes de `python main.py` |
| Avisos `Unexpected value in sys.prefix` | venv chamado por caminho relativo ou venv movido | Ativar o venv; se ele foi movido, recriar (§2) |
| "Não foi possível abrir a interface" | Sem sessão gráfica (SSH, TTY) | Rodar dentro da sessão gráfica |
| Microfone em `erro` | Sem dispositivo ou PortAudio sem acesso | `pactl info`; conferir microfone em Configurações → Som |
| "Serviço de reconhecimento indisponível" | Sem internet ou limite do Google | Verificar a conexão; tentar de novo |
| Escuta termina sem texto | Silêncio por 5 s ou fala não compreendida | Falar logo após clicar; aproximar do microfone |
| Delsin transcreve a própria voz | Escuta aberta durante a fala | Já mitigado; usar fone de ouvido se persistir |
| Voz em `erro` | `espeak-ng` não instalado | `sudo dnf install espeak-ng` |
| Ctrl+C demora a fechar | Uma escuta ou skill ainda em andamento | Aguardar o timeout correspondente (máx. 10 s) |

---

## 14. Fluxo de desenvolvimento e Git

### 14.1 Antes de todo commit

```bash
python -m unittest discover -s tests -v   # DEVE passar 100%
python main.py                            # o boot DEVE terminar sem módulo em erro inesperado
git status                                # conferir que .venv/, .env e logs NÃO aparecem
```

### 14.2 Branches

| Branch | Uso |
|---|---|
| `main` | Sempre funcional; recebe apenas merges testados |
| `feat/<nome>` | Nova funcionalidade (ex.: `feat/stt-local`) |
| `fix/<nome>` | Correção |

### 14.3 Mensagens de commit (Conventional Commits)

```
feat(skills): adiciona skill de uptime
fix(voice): libera microfone quando a rede falha
refactor(core): extrai router para arquivo próprio
docs: atualiza manual de configuração
test(core): cobre empate de score
```

Escopos válidos: `core`, `skills`, `voice`, `gui`, `config`, `docs`, `test`, `deps`.

### 14.4 Repositório remoto

```bash
git remote -v   # origin https://github.com/daniel-carvalho11/Delsin-AI.git
git push        # pede autenticação: usar um Personal Access Token (não a senha) ou SSH
```

---

## 15. Roadmap

| Fase | Entrega |
|---|---|
| 0.1 | MVP: Core, skills por palavra-chave, GUI, STT na nuvem, TTS espeak-ng ✅ |
| 0.2 | STT local (faster-whisper) e TTS Piper |
| 0.3 | `LLMRouter` usando `Persona.system_prompt` + lista de permissões de skills |
| 0.4 | Memória/contexto de conversa persistida em `~/.local/share/delsin` |
| 0.5 | Wake word ("Delsin") |
| 1.0 | Empacotamento de agentes especialistas: Core + Persona + subconjunto de skills |
