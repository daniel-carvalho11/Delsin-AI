# Delsin AI — Manual Técnico

> Assistente de IA pessoal por voz, estilo JARVIS, para Linux. Cérebro: Claude (via Claude Code, usando a sua assinatura) ou um modelo local (Ollama). Voz: ElevenLabs, Piper ou espeak-ng. Executa ações no seu PC **somente com a sua aprovação**.

| Item | Valor |
|---|---|
| Versão | 0.4.0 |
| Plataforma alvo | Linux Fedora 43, Wayland/X11 |
| Python | 3.14.x (testado em 3.14.7) |
| Repositório | https://github.com/daniel-carvalho11/Delsin-AI (público) |
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
| PipeWire + `pipewire-utils` (padrão no Fedora) | Servidor de áudio; `pw-record`/`pw-dump` capturam e listam microfones, `pw-play` toca a voz |
| **Claude Code** (§2.1) | Cérebro principal: o Delsin conversa com o Claude pelo CLI `claude`, logado na sua assinatura (Pro/Max) |
| **Ollama** (opcional, §2.3) | Cérebro alternativo 100% local e offline |
| Conta **ElevenLabs** (opcional, §2.2) | Voz neural na nuvem |

```bash
sudo dnf install python3-tkinter portaudio-devel espeak-ng gcc python3-devel
```

### 1.2 Python (`requirements.txt`, versões fixas)

| Pacote | Versão |
|---|---|
| customtkinter | 6.0.0 |
| SpeechRecognition | 3.17.0 (puxa `audioop-lts` e `standard-aifc`, removidos da stdlib no 3.13) |
| PyAudio | 0.2.14 |
| piper-tts | 1.8.0 (voz neural local; instala `onnxruntime`) |

As versões **DEVEM** permanecer fixas. Atualizar uma dependência exige: alterar `requirements.txt`, rodar os testes e testar a GUI e a voz manualmente, tudo no mesmo commit.

### 1.3 Rede

- Texto, skills e TTS: **funcionam offline**.
- STT (voz → texto): **exige internet** no MVP (serviço Google). Ver [§12](#12-limitações-e-gargalos-conhecidos).
- Download de novas vozes Piper: **exige internet** (HuggingFace, ~63 MB por voz). Depois de baixada, a voz roda offline.
- Cérebro Claude (Claude Code): **exige internet**.
- Voz ElevenLabs: **exige internet**; sem rede, o Delsin fala com o Piper automaticamente.
- Cérebro Ollama: **offline** depois de baixar o modelo (`ollama pull`, ~2 GB).

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
python -m unittest discover -s tests -v   # 41 testes, todos OK (sem rede e sem gastar cota)
```

5. Na primeira execução, abra **♪ → Motor: Piper → Voz: Faber → BAIXAR VOZ** (63 MB). Até lá o Delsin usa o espeak-ng automaticamente.
6. Em **♪ → Microfone**, escolha a entrada e clique em **TESTAR MICROFONE** (§4.6.1).

### 2.1 Cérebro Claude (assinatura via Claude Code) — padrão

O Delsin não usa API key: ele abre o `claude` (Claude Code) em modo não interativo, logado na sua conta claude.ai. O uso conta para os limites do seu plano (Pro/Max), **sem cobrança extra**.

```bash
# 1. Instalar o Claude Code (se ainda não tiver)
curl -fsSL https://claude.ai/install.sh | bash

# 2. Logar com a sua conta (abre o navegador) e sair
claude

# 3. Conferir: deve mostrar "loggedIn": true e "authMethod": "claude.ai"
claude auth status
```

- Modelo padrão: `claude-opus-5-5` com esforço `low` (respostas mais rápidas para voz). Trocar: `DELSIN_CLAUDE_MODEL`, `DELSIN_CLAUDE_EFFORT` (`low`…`max`).
- O Delsin **remove** `ANTHROPIC_API_KEY` do ambiente do `claude`, para o uso nunca cair numa cobrança por API sem você perceber.
- O que o Claude pode fazer sozinho e o que exige sua aprovação: §4.9.

### 2.2 Voz ElevenLabs (opcional)

1. Crie uma conta em elevenlabs.io (o plano gratuito tem ~10 min de fala/mês; o Starter custa ~US$ 5–6/mês).
2. Gere uma chave em **Developers → API Keys**. Permissões mínimas: *Text to Speech* e *Voices (read)*.
3. No Delsin: **♪ → ElevenLabs → cole a chave → SALVAR CHAVE**. Ela é validada na hora e gravada em `~/.config/delsin/secrets.env` (permissão 0600, **fora do repositório**).
4. **Motor: ElevenLabs → Voz → TESTAR VOZ → SALVAR.**

Sem créditos, sem internet ou com a chave inválida, cada fala cai automaticamente para o Piper (e, sem ele, para o espeak-ng).

### 2.3 Cérebro local (Ollama, opcional)

Para usar: `DELSIN_BRAIN=ollama python main.py`. O modo local não tem internet nem executa ações.

```bash
# 1. Instalar o Ollama (serviço systemd "ollama", escuta só em 127.0.0.1:11434)
curl -fsSL https://ollama.com/install.sh | sh

# 2. Conferir o serviço
systemctl status ollama --no-pager
ollama --version

# 3. Baixar o modelo padrão do Delsin (~1,9 GB)
ollama pull qwen2.5:3b

# 4. Testar fora do Delsin
ollama run qwen2.5:3b "Responda em uma frase: o que é o Fedora?"
```

Depois disso, reinicie o Delsin: o módulo **IA · LLM** deve ficar `ONLINE`.

| Modelo | Download | RAM | Velocidade na CPU (i7-13620H) | Observação |
|---|---|---|---|---|
| `qwen2.5:3b` (**padrão**) | 1,9 GB | ~3 GB | rápido (~15–20 tokens/s) | Bom português para o tamanho |
| `llama3.2:3b` | 2,0 GB | ~3 GB | rápido | Alternativa |
| `qwen2.5:7b` | 4,7 GB | ~6 GB | lento (~6–9 tokens/s) | Melhor qualidade; só com RAM livre |

Trocar o modelo: `ollama pull <modelo>` e iniciar com `DELSIN_LLM_MODEL=<modelo> python main.py`.

**GPU (opcional):** sem o driver proprietário da NVIDIA, o Ollama roda **só na CPU**. Com o driver (RPM Fusion: `akmod-nvidia` + `xorg-x11-drv-nvidia-cuda`), a RTX 3050 6 GB é usada automaticamente e modelos 3B–7B ficam várias vezes mais rápidos. A instalação de driver altera o sistema (Secure Boot pode exigir assinar o módulo); faça com calma.

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
┌─────────────────────────────────────────────────────────────────────┐
│ (◎) D E L S I N                       CARGA GLOBAL ▬▬▬▭▭   [♪] [>_] │
├──────────────────────┬──────────────────────┬───────────────────────┤
│ ┌ CORE SYSTEMS ────┐ │ ┌ CONSOLE NEURAL ──┐ │ ┌ PROTOCOLO TEMPORAL ┐│
│ │ CPU / MEM / DISCO│ │ │ CONVERSA | LOG   │ │ │ calendário + hora  ││
│ │ TEMP / CARGA     │ │ │                  │ │ │ sessão: comandos,  ││
│ └──────────────────┘ │ │ mensagens        │ │ │ latência, uptime   ││
│ ┌ MÓDULOS ─────────┐ │ │                  │ │ └────────────────────┘│
│ │ núcleo, skills,  │ │ └──────────────────┘ │ ┌ NEURAL TRACE ──────┐│
│ │ stt, tts, llm    │ │ ┌──────────────────┐ │ │ animação de estado ││
│ │ [voz] [config.]  │ │ │ campo [OUVIR][>] │ │ │ ESTADO NEURAL · …  ││
│ └──────────────────┘ │ └──────────────────┘ │ └────────────────────┘│
├──────────────────────┴──────────────────────┴───────────────────────┤
│ PYTHON · KERNEL · SO                  DELSIN OS V0.2.0 / OPERACIONAL │
└─────────────────────────────────────────────────────────────────────┘
```

A janela abre maximizada. Tamanho mínimo: 1280×800.

### 4.1 Painéis

| Painel | Conteúdo | Atualização |
|---|---|---|
| (IA · LLM no painel Módulos) | `ollama <versão> · <modelo>` e tokens/s da última resposta, ou o motivo da falha | Por evento |
| Core Systems | CPU, memória, disco (`~`), temperatura, carga média | A cada 2 s (`services/telemetry.py`) |
| Módulos | Estado de cada módulo + detalhe; switch de voz; botão de configuração de voz | Por evento |
| Console Neural | Abas **CONVERSA** (últimas 300 mensagens) e **LOG** (últimas 1500 linhas) | Por evento |
| Barra de comando | Campo de texto, **OUVIR**, **ENVIAR** | — |
| Protocolo Temporal | Calendário do mês, hora do sistema, estatísticas da sessão | A cada 1 s |
| Neural Trace | Animação do estado atual do assistente | 30 fps ativo / 15 fps ocioso |
| Cabeçalho | Carga global (5 segmentos = CPU), **♪** voz, **>_** alterna conversa/log | — |
| Rodapé | Versões do sistema; `SISTEMA OPERACIONAL` ou `OPERANDO COM RESTRIÇÕES` se algum módulo estiver em erro | Por evento |

Barras de métrica mudam de cor: ≥ 85% âmbar, ≥ 95% vermelho.

### 4.2 Estados dos módulos

| Cor | Estado | Significado |
|---|---|---|
| Cinza | `OFFLINE` | Não configurado ou desligado |
| Âmbar | `INICIANDO` | Verificando dependências, dispositivos ou baixando voz |
| Verde | `ONLINE` | Pronto |
| Azul | `ATIVO` | Em operação (ex.: microfone ouvindo) |
| Vermelho | `ERRO` | Falhou; o motivo aparece abaixo do nome e no log |

Uma falha de voz **não** derruba o sistema: o Delsin continua em modo texto.

### 4.3 Estados neurais (Neural Trace)

| Estado | Cor | Animação | Origem |
|---|---|---|---|
| `OCIOSO` | Branco | Núcleo "respirando" devagar | Nenhuma atividade |
| `PROCESSANDO` | Âmbar | Anel tracejado gira rápido | Comando aguardando resposta do Core |
| `OUVINDO` | Azul | Ondas expandindo a partir do centro | Microfone aberto |
| `FALANDO` | Verde | Forma de onda + núcleo pulsando | Áudio sendo reproduzido |

Prioridade quando há mais de um ao mesmo tempo: FALANDO > OUVINDO > PROCESSANDO > OCIOSO.

### 4.4 Atalhos

| Tecla / botão | Ação |
|---|---|
| `Enter` (no campo) | Envia o texto digitado |
| `Ctrl+Espaço` | Inicia uma escuta (igual a **OUVIR**) |
| **♪** | Abre a configuração de voz |
| **>_** | Alterna entre CONVERSA e LOG |

### 4.5 Quando o Delsin fala

A resposta é falada se **todas** as condições forem verdadeiras:

1. O módulo **VOZ · TTS** está `ONLINE`;
2. A skill não marcou a resposta como `speak=False` (ex.: `help`);
3. O switch **RESPONDER POR VOZ** está ligado **ou** o comando veio pelo microfone.

Ao clicar em **OUVIR**, qualquer fala em andamento é interrompida (evita que o Delsin transcreva a própria voz).

### 4.6 Configuração de voz e microfone (botão ♪ ou CONFIGURAR VOZ)

#### 4.6.1 Microfone

| Controle | Efeito |
|---|---|
| Microfone | **Padrão do sistema** (segue o Fedora) ou uma entrada específica: embutido, fone, USB, Bluetooth |
| TESTAR MICROFONE | Grava 3 s da entrada escolhida e mostra o pico: **Sem sinal** (< 0,6%), **Sinal fraco** (< 5%) ou **Sinal bom** |

- A escolha é salva com o perfil (**SALVAR**) e vale para o botão **OUVIR**.
- Se uma escuta terminar com entrada muda, o Delsin avisa na conversa: *"O microfone não está captando som…"*.
- **Fones sem microfone:** ao conectar um fone na entrada P2, o Fedora costuma trocar a entrada padrão para o microfone da porta do fone (`Stereo Microphone`). Se o fone não tem microfone, essa entrada fica muda. Escolha **Digital Microphone** (microfones embutidos) no Delsin.

#### 4.6.2 Voz

| Controle | Faixa | Efeito |
|---|---|---|
| Motor | ElevenLabs (nuvem) / Piper (neural) / espeak-ng (leve) | ElevenLabs: a mais natural, vozes femininas e masculinas, pago por caractere. Piper: natural e offline. espeak: robótico, offline |
| ElevenLabs | campo da chave + SALVAR CHAVE | Valida e grava a chave fora do repositório; a chave nunca é exibida de volta (só `abcd…wxyz`) |
| Voz | Lista do motor | Vozes Piper não instaladas aparecem como `[não instalada]` e liberam **BAIXAR VOZ** |
| Velocidade | 0.60× – 1.60× | Ritmo da fala |
| Tom | −25% – +30% | Mais grave ↔ mais agudo |
| Volume | 20% – 150% | Ganho aplicado na síntese (acima de 100% pode distorcer) |
| Frase | texto livre | Frase usada em **TESTAR** |

- **TESTAR** toca a frase com os valores da tela **sem** salvar.
- **SALVAR** aplica a todas as respostas seguintes e grava em `~/.local/share/delsin/voice_profile.json`.
- **BAIXAR VOZ** baixa do catálogo oficial do Piper; o progresso aparece no log e no módulo VOZ · TTS.

Vozes disponíveis:

| Motor | Vozes pt-BR |
|---|---|
| Piper | Faber, Cadu, Jeff (qualidade média), Edresson (baixa). **Todas masculinas** — o catálogo oficial não tem voz feminina pt-BR |
| espeak-ng | Padrão, Masculina 1/3/7, Henrique, Marcelo, Diogo, Feminina 1/2/4, Klatt, Sussurro |

### 4.7 Comandos disponíveis

| Skill | Palavras-gatilho (acentos ignorados) | Exemplo |
|---|---|---|
| `clock` | hora, horas, horário, data, que dia, hoje | "que horas são?", "que dia é hoje?" |
| `system_status` | status, diagnóstico, sistema, memória, cpu | "status do sistema" |
| `help` | ajuda, help, comandos, o que você faz, skills | "ajuda" |

| `llm` | qualquer frase sem gatilho acima; "nova conversa" apaga o contexto | "olá, tudo bem?", "pesquise a previsão do tempo", "abra a calculadora" |

Cada resposta exibe `ok|falha · skill · latência em ms`.

### 4.8 Conversa com o cérebro

- **Ordem de decisão:** as skills de palavra-chave respondem primeiro (instantâneas e sem custo). Só o que nenhuma reconhece vai para o cérebro.
- **Claude (padrão):** uma única sessão do Claude Code fica aberta enquanto o Delsin roda, então ele lembra de toda a conversa. Pode **pesquisar na web**, **ler arquivos** e rodar **comandos de consulta** (df, free, ls, ps…) sem pedir. Respostas típicas: 3–6 s.
- **Ollama:** últimos 8 pares pergunta/resposta em memória; sem internet e sem ações.
- **"nova conversa"** (ou "limpar contexto") apaga o contexto. Nada da conversa é salvo em disco (`--no-session-persistence`).
- **Estilo:** português do Brasil, no máximo 3 frases curtas, sem markdown (as respostas podem ser faladas). Peça "detalhe" para respostas maiores.
- **Cérebro fora do ar:** a resposta explica o motivo e o módulo IA · LLM fica `ERRO`. A sessão do Claude se recria sozinha na próxima pergunta.

### 4.9 Ações no computador (com aprovação)

```
você: "abra a calculadora"
  → Claude tenta: Bash("setsid -f gnome-calculator")
  → Claude Code BLOQUEIA (modo dontAsk) e devolve o pedido exato
  → Delsin mostra o cartão  AÇÃO AGUARDANDO APROVAÇÃO  ▸ Executar comando: setsid -f gnome-calculator
  → [APROVAR] → o PRÓPRIO Delsin executa exatamente esse texto → o resultado volta ao Claude → resposta falada
  → [RECUSAR] → nada roda; o Claude é avisado
```

| O Claude faz **sem pedir** | Exige **sua aprovação** no cartão | **Nunca** |
|---|---|---|
| Ler arquivos (Read/Glob/Grep) | Qualquer outro comando de terminal | Ler `~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.config/delsin`, chaveiros, perfis de navegador, `*.env`, `*.pem`, `*.key` |
| Pesquisar e abrir páginas da web | Criar/substituir arquivos (Write) | `sudo` (sem terminal para senha; falha) |
| `df`, `free`, `uptime`, `uname`, `lscpu`, `lsblk`, `ps`, `date`, `whoami`, `hostnamectl`, `nvidia-smi`, `sensors`, `ls`, `du`, `which`, `ip addr`, `systemctl status`, `wpctl status` | Editar arquivos (Edit) — só dentro da sua pasta pessoal | Escrever fora da pasta pessoal |

Regras do executor (`services/actions.py`):
- Executa **exatamente** o texto mostrado no cartão, com `bash -c`, na sua pasta pessoal, em nova sessão de processos.
- Timeout de 120 s (o grupo de processos inteiro é encerrado); programas abertos em segundo plano continuam rodando.
- Várias ações no mesmo cartão rodam em ordem e **param na primeira falha**.
- A aprovação é **só por clique**, nunca por voz (um áudio de TV não pode aprovar nada).

---

## 5. Arquitetura

### 5.1 Estrutura

```
delsin/
├── main.py              # Composition root: instancia e liga módulos, controla threads
├── requirements.txt
├── config/
│   ├── settings.py      # Settings imutáveis + caminhos XDG (pathlib)
│   ├── persona.py       # Mensagens, system prompt e capacidades por cérebro
│   ├── secrets.py       # Chaves de API em ~/.config/delsin/secrets.env (0600)
│   └── voice_profile.py # VoiceProfile (motor/voz/tom/velocidade/volume) + JSON atômico
├── core/
│   ├── contracts.py     # Request, Response, Skill, SkillContext, SkillInfo, Source
│   ├── agent.py         # Agent (execução) + Router (estratégia de escolha)
│   └── logger.py        # Arquivo rotativo + terminal + fila da GUI
├── skills/
│   ├── __init__.py      # discover_skills(): auto-descoberta de plugins
│   ├── _base.py         # KeywordSkill (base, não descoberta)
│   └── builtin.py       # clock, system_status, help
├── services/
│   ├── telemetry.py     # CPU, memória, disco, temperatura, carga (/proc, /sys)
│   └── actions.py       # ActionRunner: executa ações APROVADAS (Bash/Write/Edit)
├── llm/
│   ├── brain.py         # Contrato Brain + PendingAction (ações bloqueadas)
│   ├── claude_code.py   # ClaudeCodeBrain: sessão `claude -p` stream-json + política de permissões
│   ├── ollama.py        # OllamaClient + OllamaBrain (local, só loopback)
│   └── conversation.py  # ConversationSkill: fallback do Agent, reset, follow_up
├── voice/
│   ├── stt.py           # SpeechToText (backends PipeWire e PyAudio)
│   ├── capture.py       # PipeWireSource (pw-record) + medição de nível
│   ├── devices.py       # Lista de microfones via pw-dump
│   ├── tts.py           # TextToSpeech: fila, perfil, fallback, interrupção
│   ├── engines.py       # ElevenLabsEngine, PiperEngine e EspeakEngine → PCM
│   ├── player.py        # PcmPlayer (pw-play > paplay > aplay em subprocesso)
│   └── alsa.py          # Silencia o ruído da libasound no stderr
├── gui/
│   ├── dashboard.py     # Janela principal (layout HUD em 3 colunas)
│   ├── widgets.py       # HudPanel, GridSurface, calendário, Neural Trace, métricas
│   ├── voice_dialog.py  # Janela de configuração de voz
│   ├── events.py        # Eventos thread → GUI
│   └── theme.py         # Paleta, fonte, track() e blend()
└── tests/
    ├── test_agent.py
    ├── test_voice.py
    ├── test_llm.py      # Claude Code falso (fake_claude.py) + Ollama falso
    ├── test_services.py # executor de ações, segredos, ElevenLabs falso
    └── fake_claude.py   # imita o protocolo stream-json do `claude -p`
```

### 5.2 Regras de dependência (obrigatórias)

```
                 main.py  (único que importa todos)
      ┌───────┬──────┼─────────┬──────────┐
      ▼       ▼      ▼         ▼          ▼
    gui/   voice/  services/  skills/ ──► core/ ◄── llm/
      │       │                            │
      └───────┴──────────► config/ ◄───────┘
```

| Módulo | PODE importar | NÃO DEVE importar |
|---|---|---|
| `config/` | stdlib | qualquer outro módulo do projeto |
| `core/` | `config/`, stdlib | `gui/`, `voice/`, `skills/` |
| `skills/` | `core.contracts`, `skills._base`, stdlib | `gui/`, `voice/`, `core.agent` |
| `voice/` | `config/`, stdlib, piper | `core/`, `gui/`, `skills/`, `services/` |
| `services/` | stdlib | qualquer outro módulo do projeto |
| `llm/` | `core.contracts`, `config/`, stdlib | `gui/`, `voice/`, `skills/`, `core.agent` |
| `gui/` | `config/`, `core.logger` (só o tipo `LogItem`), stdlib, customtkinter | `core.agent`, `voice/`, `skills/`, `services/` |
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
                    │     └─ nenhuma      → fallback = LLM (timeout 120 s)
                    │                       (sem LLM configurada → Response(fallback, falha))
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
| `delsin-tts` | Fila de fala → síntese (Piper/espeak) → subprocesso `pw-play` | Não |
| `delsin-voice-load` | Carrega o modelo Piper ao trocar de voz | Não |
| `delsin-voice-dl` | Download de vozes (sob demanda) | Não |
| `delsin-telemetry` | Amostra métricas do host a cada 2 s | Não |
| `delsin-mic-test` | Teste de nível do microfone (sob demanda) | Não |
| `delsin-claude-out` / `-err` | Leem a saída do processo `claude -p` | Não |
| `delsin-action` | Executa ações aprovadas e devolve o resultado ao cérebro | Não |
| `delsin-key` | Valida a chave da ElevenLabs | Não |
| `delsin-boot` (fim) | Conecta ao Ollama e pré-carrega o modelo | Não |

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
| `fallback_timeout_s` | 200.0 | Tempo máximo do cérebro (pesquisas e leituras do Claude; CPU no Ollama) |

### 8.1.1 `LLMSettings`

| Campo | Padrão | Efeito |
|---|---|---|
| `enabled` | `True` | `DELSIN_LLM_DISABLED=1` desliga |
| `brain` | `claude` | `claude` (assinatura via Claude Code) ou `ollama` (`DELSIN_BRAIN`) |
| `claude_model` | `claude-opus-5-5` | Modelo do Claude (`DELSIN_CLAUDE_MODEL`) |
| `claude_effort` | `low` | Esforço de raciocínio: `low`…`max` (`DELSIN_CLAUDE_EFFORT`); mais alto = mais lento e mais cota |
| `claude_timeout_s` | 180.0 | Sem resposta nesse tempo → a sessão é reiniciada |
| `base_url` | `http://127.0.0.1:11434` | Servidor Ollama |
| `model` | `qwen2.5:3b` | Modelo usado (`DELSIN_LLM_MODEL`) |
| `temperature` | 0.6 | Criatividade |
| `context_tokens` | 4096 | Janela de contexto (`num_ctx`) |
| `max_response_tokens` | 320 | Limite de tamanho da resposta (`num_predict`) |
| `history_turns` | 8 | Pares pergunta/resposta mantidos |
| `request_timeout_s` | 120.0 | Timeout HTTP |
| `keep_alive` | `30m` | Tempo que o Ollama mantém o modelo carregado após o último uso |
| `allow_remote` | `False` | Só loopback; `DELSIN_LLM_ALLOW_REMOTE=1` libera outro host |

### 8.2 `VoiceSettings`

| Campo | Padrão | Efeito |
|---|---|---|
| `language` | `pt-BR` | Idioma do STT |
| `preferred_input_devices` | `("pipewire", "default")` | Nomes exatos de dispositivo, em ordem de preferência |
| `ambient_calibration_s` | 0.5 | Calibração de ruído antes de cada escuta |
| `listen_timeout_s` | 5.0 | Espera máxima pelo início da fala |
| `phrase_time_limit_s` | 10.0 | Duração máxima de uma frase |
| `recognition_timeout_s` | 8.0 | Timeout da chamada de rede do STT |
| `tts_synthesis_timeout_s` | 30.0 | Tempo máximo de síntese do espeak-ng |
| `voice_download_timeout_s` | 300.0 | Tempo máximo do download de uma voz Piper |
| `tts_queue_size` | 10 | Falas pendentes; excedentes são descartadas com aviso |
| `elevenlabs_model` | `eleven_flash_v2_5` | Modelo da ElevenLabs (baixa latência, multilíngue) |
| `elevenlabs_timeout_s` | 20.0 | Timeout HTTP de cada fala |

### 8.2.1 `VoiceProfile` (`config/voice_profile.py`, editável pela GUI)

| Campo | Padrão | Faixa | Observação |
|---|---|---|---|
| `engine` | `piper` | `piper`, `espeak` | Valor inválido vira `espeak` |
| `voice` | `pt_BR-faber-medium` | id do motor | Ids Piper são validados por regex (impede path traversal) |
| `rate` | 1.0 | 0.60 – 1.60 | Valores fora da faixa são limitados |
| `pitch` | 1.0 | 0.75 – 1.30 | idem |
| `volume` | 1.0 | 0.20 – 1.50 | idem |
| `input_device` | `""` | nome do nó PipeWire | `""` = padrão do sistema; nomes com caracteres fora de `[\w.\-:@]` são descartados |

O arquivo é gravado de forma atômica (temporário + rename). Arquivo ausente, corrompido ou com campos desconhecidos → perfil padrão, sem travar o boot.

### 8.3 Variáveis de ambiente

| Variável | Efeito |
|---|---|
| `DELSIN_DEBUG=1` | Logs em nível DEBUG (inclui o score de roteamento) |
| `DELSIN_LANG` | Idioma do STT. **Não** altera a voz do TTS |
| `DELSIN_BRAIN` | `claude` (padrão) ou `ollama` |
| `DELSIN_CLAUDE_MODEL` | Modelo do Claude (padrão `claude-opus-5-5`) |
| `DELSIN_CLAUDE_EFFORT` | `low` (padrão), `medium`, `high`, `xhigh`, `max` |
| `ELEVENLABS_API_KEY` | Chave da ElevenLabs (tem prioridade sobre o arquivo de segredos) |
| `DELSIN_LLM_MODEL` | Modelo do Ollama (padrão `qwen2.5:3b`) |
| `DELSIN_LLM_URL` | Endereço do Ollama (padrão `http://127.0.0.1:11434`) |
| `DELSIN_LLM_DISABLED=1` | Desliga a LLM |
| `DELSIN_LLM_ALLOW_REMOTE=1` | Permite Ollama fora de localhost (os textos trafegam pela rede) |
| `XDG_DATA_HOME` | Base dos dados (padrão `~/.local/share`) |
| `XDG_CACHE_HOME` | Base do cache (padrão `~/.cache`) |

### 8.4 Caminhos

| Caminho | Conteúdo | Permissão |
|---|---|---|
| `~/.local/share/delsin/` | Dados do usuário | `0700` |
| `~/.local/share/delsin/logs/` | Logs | `0700` |
| `~/.local/share/delsin/voices/` | Modelos Piper (`.onnx` + `.onnx.json`, ~63 MB cada) | `0700` |
| `~/.local/share/delsin/voice_profile.json` | Perfil de voz salvo | herdada |
| `~/.config/delsin/secrets.env` | Chaves de API (ElevenLabs) | `0600` (pasta `0700`) |
| `~/.cache/delsin/` | Cache (reservado) | `0700` |

As pastas são criadas na inicialização (`ensure_dirs()`), e a permissão é reaplicada a cada execução.

### 8.5 Personalidade (`config/persona.py`)

Contém todas as mensagens fixas (saudação, fallback, erros) e o `system_prompt` que será enviado ao LLM quando integrado. Para criar um agente especialista, instancie outro `Persona` e passe ao `Agent`. **NÃO** espalhe texto de personalidade pelas skills.

---

## 9. Módulo de voz

### 9.1 STT (`voice/stt.py`, `capture.py`, `devices.py`)

**Backend PipeWire (padrão quando `pw-record` e `pw-dump` existem):**

1. No boot: lista os microfones com `pw-dump` (nós `Audio/Source`) e marca o padrão do sistema. Microfone salvo que sumiu (ex.: fone desconectado) → volta ao padrão, com aviso no log.
2. Em cada escuta: `pw-record --raw --rate 16000 --channels 1 --format s16 [--target <microfone>] -` em subprocesso → calibra o ruído (0,5 s) → espera a fala (até 5 s) → grava (até 10 s) → **encerra o pw-record** → envia para transcrição (até 8 s).
3. **Watchdog:** se o pw-record parar de entregar áudio, ele é morto após o tempo máximo da escuta, e a captura nunca trava.
4. **Detecção de entrada muda:** o pico de cada escuta é medido. Pico < 0,6% → mensagem de erro clara em vez de "não entendi".
5. Só uma captura por vez (escuta **ou** teste de microfone).

**Backend PyAudio (reserva, sem PipeWire):** abre o dispositivo `pipewire`/`default` do ALSA; sem escolha de microfone nem medição de nível. Abrir dispositivos `hw:X,Y` diretamente **NÃO DEVE** ser feito: eles competem com o servidor de áudio.

Diagnóstico pelo terminal:

```bash
wpctl status                                  # entradas (Sources) e a padrão (*)
pactl get-default-source
wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 0.9   # volume de entrada para 90%
```

### 9.2 TTS (`voice/tts.py`, `engines.py`, `player.py`)

```
texto → fila (delsin-tts) → motor (PCM 16-bit mono) → PcmPlayer (subprocesso pw-play)
```

- **Motor e reprodução são separados.** O motor só gera áudio; o player toca. Interromper = matar um processo.
- **Piper** roda no próprio processo: carrega o modelo uma vez (~1,3 s, feito no boot e ao trocar de voz) e sintetiza cada frase em ~0,1 s. Apenas **um** modelo fica em memória (~100 MB de RAM).
- **Tom no Piper:** o Piper não tem controle de tom. O Delsin toca o áudio a uma taxa `× tom` (sobe/desce o tom) e alonga os fonemas na mesma proporção (`length_scale = tom / velocidade`), mantendo a duração. Em valores extremos o timbre fica artificial.
- **espeak-ng** roda como subprocesso com `--stdout`; tom (`-p`), velocidade (`-s`) e amplitude (`-a`) são nativos.
- O texto entra **por stdin** no espeak-ng, nunca como argumento.
- **Fallback:** se o motor ou a voz do perfil não estiverem disponíveis, a fala usa `espeak-ng pt-br` com o mesmo tom, velocidade e volume, e o log registra um aviso.
- **Interrupção:** `stop()` incrementa uma "época"; falas enfileiradas ou em síntese de épocas anteriores são descartadas, e o player atual é encerrado (SIGTERM).
- **Download de vozes:** só ids do catálogo (`PIPER_CATALOG`). O download vai para uma pasta temporária e só é movido ao final, então uma queda de rede não deixa modelo truncado.
- O `pyttsx3` **NÃO DEVE** ser usado: o `runAndWait()` dele trava no Linux quando chamado por threads.

Testes isolados:

```bash
echo "teste de voz" | espeak-ng -v pt-br --stdin
python -c "from voice.engines import *; print('ok')"
```

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
| S2 | Chaves de API **DEVEM** ficar em `~/.config/delsin/secrets.env` (0600) ou em variável de ambiente; **NUNCA** no código, no README, em issues ou em capturas de tela | O repositório é **público** |
| S3 | Nenhuma skill **DEVE** executar comandos de shell montados com texto do usuário | Injeção de comandos |
| S4 | Todo texto vindo de voz ou de LLM **DEVE** ser tratado como não confiável | Injeção de prompt e comandos por áudio de terceiros (TV, vídeo, outra pessoa) |
| S5 | Skills com efeito colateral (arquivos, rede, sistema) **DEVEM** pedir confirmação explícita na GUI | Uma transcrição errada não pode virar uma ação destrutiva |
| S6 | Quando um LLM for integrado, as skills que ele puder acionar **DEVEM** estar numa lista de permissões | Limita o raio de dano de uma resposta maliciosa |
| S7 | Antes de todo push: `git diff --cached` e conferir que não há chaves, e-mails ou caminhos pessoais. Se uma chave vazar, **revogue-a na hora** no painel do serviço (apagar o commit não basta) | Repositório público é indexado e copiado em minutos |
| S8 | Vozes Piper **DEVEM** vir do catálogo oficial (`PIPER_CATALOG`); o id é validado antes de virar caminho | O perfil é um JSON editável; ids como `../../x` não podem escapar de `voices/` |
| S9 | Modelos de voz são ONNX (dados, não código executável). **NÃO** carregue modelos `.pt`/pickle de fontes desconhecidas | Pickle executa código ao carregar |
| S10 | O cliente do Ollama **só** aceita servidores em loopback (salvo `DELSIN_LLM_ALLOW_REMOTE=1`) e ignora `http_proxy` | Conversas não saem da máquina por engano |
| S11 | Ações que modificam o sistema **DEVEM** passar pelo cartão de aprovação; o Claude Code roda em `--permission-mode dontAsk` com lista de permissões só de leitura | Texto vindo de voz, de páginas web ou da própria LLM é não confiável (injeção de prompt) |
| S13 | **NUNCA** usar `--dangerously-skip-permissions` nem liberar `Bash` sem padrão no Claude Code do Delsin | Daria ao modelo execução livre na sua conta |
| S14 | O Claude Code do Delsin roda com `--safe-mode` (ignora CLAUDE.md, hooks, plugins e MCP pessoais) e sem `ANTHROPIC_API_KEY` | Isolamento e cobrança previsível (assinatura) |
| S15 | Caminhos sensíveis (`~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.config/delsin`, chaveiros, navegadores, `*.env`, `*.pem`, `*.key`) são **negados** para leitura | O que o Claude lê vai para a Anthropic |
| S12 | O histórico da conversa fica só em memória; não é gravado em disco nem em log | Privacidade |

**Privacidade — o que sai da sua máquina:**

| Destino | O que recebe |
|---|---|
| Anthropic (Claude, via sua assinatura) | Suas mensagens, o histórico da sessão, o conteúdo dos arquivos que o Claude ler e a saída dos comandos executados |
| ElevenLabs (se escolhida) | O texto de cada resposta falada |
| Google (reconhecimento de voz) | O áudio de cada comando de voz |
| Ollama / Piper / espeak | Nada — tudo local |

---

## 12. Limitações e gargalos conhecidos

| Item | Impacto | Mitigação planejada |
|---|---|---|
| STT na nuvem (Google) | +1 a 3 s por comando; exige internet; envia áudio para terceiros | `faster-whisper` ou Vosk local |
| Calibração por escuta | +0,5 s por comando | Calibrar uma vez e recalibrar periodicamente |
| Timeout de skill não mata a thread | Uma skill travada continua consumindo uma das 4 threads | Skills pesadas em subprocesso |
| Empate de score | Vence a skill registrada primeiro (ex.: "status do sistema hoje") | Router por LLM ou por pesos |
| Gatilho por palavra-chave | Não entende paráfrases | Router por LLM |
| Piper: só vozes masculinas pt-BR | Sem voz feminina natural | Ajustar o tom; treinar/obter um modelo feminino pt-BR |
| Piper: modelo em memória | ~100 MB de RAM; 1,3 s ao trocar de voz | Aceitável; só um modelo carregado por vez |
| Tom no Piper por reamostragem | Timbre artificial em valores extremos | Faixa limitada a −25%/+30% |
| Síntese Piper não tem timeout | Uma frase enorme bloqueia a fila de fala | Entradas limitadas a 2000 caracteres |
| Animação do Neural Trace | ~1–2% de CPU a 30 fps | 15 fps quando ocioso |
| Claude via assinatura | 3–6 s por resposta (Opus, esforço low); conta nos limites do plano; ao atingir o limite, as respostas falham até o reset | Esforço `low`; skills locais respondem o básico sem gastar cota; Ollama como reserva |
| Sem streaming de resposta | O texto aparece e é falado só no fim | Streaming por frase (roadmap) |
| Ações: só Bash, Write e Edit | Outras ferramentas bloqueadas são ignoradas | — |
| Aprovação só por clique | Não dá para aprovar por voz | Intencional (segurança) |
| ElevenLabs cobra por caractere | Respostas longas gastam créditos | Respostas curtas por padrão; fallback para Piper |
| LLM só na CPU (Ollama sem driver NVIDIA) | 3–10 s por resposta | Modelo 3B, pré-carregamento, driver NVIDIA |
| Sem streaming de resposta | A resposta aparece (e é falada) só quando termina | Streaming token a token (roadmap) |
| LLM ocupa RAM | ~3 GB com `qwen2.5:3b` carregado, liberada após 30 min sem uso | Ajustar `keep_alive` |
| Modelos 3B erram fatos | Respostas confiantes e erradas são possíveis | Modelo maior / GPU; nunca usar para decisões críticas |
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
| Voz em `erro` | Sem motor ou sem player | `sudo dnf install espeak-ng`; `pip install -r requirements.txt`; conferir `which pw-play` |
| Log "Voz … indisponível — usando espeak-ng" | Voz Piper do perfil não instalada | ♪ → selecionar a voz → **BAIXAR VOZ** |
| "Falha no download" | Sem internet ou HuggingFace fora do ar | Tentar de novo; o download parcial é descartado automaticamente |
| Fonte do painel diferente das capturas | JetBrains Mono não instalada | `sudo dnf install jetbrains-mono-fonts-all` e reiniciar o Delsin |
| "O microfone não está captando som" | Entrada muda (ex.: porta do fone sem microfone) | ♪ → Microfone → escolha outra → TESTAR MICROFONE → SALVAR |
| Teste de microfone com "Sinal fraco" | Volume de entrada baixo | `wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 0.9` ou Configurações → Som → Entrada |
| IA · LLM: "Claude Code não encontrado" | CLI não instalado ou fora do PATH | §2.1 |
| IA · LLM: "sem login" / "logado via … não pela assinatura" | Claude Code deslogado ou logado por API key | `claude` → `/login` com a conta claude.ai; conferir `claude auth status` |
| Respostas do Claude falhando de repente | Limite de uso do plano atingido | Aguardar o reset do plano; usar `DELSIN_BRAIN=ollama` enquanto isso |
| "O Claude demorou demais e a sessão foi reiniciada" | Pesquisa/leitura longa ou instabilidade | Repetir; perguntas mais objetivas |
| Ação aprovada "FALHOU" | Comando inválido, sem permissão ou precisa de `sudo` | Ler a saída no log; pedir outra forma ao Delsin |
| ElevenLabs: "chave inválida" / "créditos esgotados" | Chave errada / plano sem créditos | Gerar nova chave; ver créditos em elevenlabs.io (o Delsin fala com o Piper enquanto isso) |
| IA · LLM: "Ollama inacessível … Connection refused" | Ollama não instalado ou parado (só com `DELSIN_BRAIN=ollama`) | §2.3; `sudo systemctl start ollama` |
| IA · LLM: "modelo … não baixado" | Modelo ausente | `ollama pull qwen2.5:3b` |
| Resposta da LLM muito lenta | Rodando na CPU / pouca RAM livre | Feche apps pesados; use um modelo 3B; driver NVIDIA (§2.3) |
| LLM responde em inglês ou longo demais | Modelo pequeno ignorando instruções | Peça de novo; troque de modelo (`DELSIN_LLM_MODEL`) |
| Painel lento ao arrastar/redimensionar | Redesenho do grid de fundo | Esperado durante o redimensionamento; para quando a janela para |
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
| 0.2 | Painel HUD, telemetria, TTS Piper com perfil de voz configurável ✅ |
| 0.3 | Escolha de microfone com teste de nível; LLM local (Ollama) como fallback conversacional ✅ |
| 0.4 | Cérebro Claude via assinatura (Claude Code), ações no PC com aprovação, voz ElevenLabs ✅ |
| 0.4.x | Streaming por frase (texto e voz começam antes do fim); escolha do cérebro/modelo na GUI; wake word "Delsin" |
| 0.5 | STT local (faster-whisper); memória de longo prazo opt-in |
| 0.4.x | Memória de conversa persistida (opcional, criptografada) em `~/.local/share/delsin` |
| 0.5 | Wake word ("Delsin") |
| 1.0 | Empacotamento de agentes especialistas: Core + Persona + subconjunto de skills |

---

## Créditos e inspiração

A ideia de usar o Claude Code (logado na assinatura) como cérebro de um assistente por voz estilo JARVIS foi inspirada no vídeo *"Turn Your Claude Code into JARVIS From Ironman"* e em projetos da comunidade como [ethanplusai/jarvis](https://github.com/ethanplusai/jarvis) (macOS). O código do Delsin é independente e foi escrito para Linux/Fedora.

