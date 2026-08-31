# YouTube Prospector — Extensão Chrome, API Central & Painel de Horas

Sistema profissional para prospecção, detecção e coleta de canais do YouTube em equipe (~10 usuários simultâneos) com prevenção de duplicidades em tempo real, controle de sessões de trabalho, sistema de ciclos, ritmo de coleta (canais/h) e ranking de horas trabalhadas.

---

## 🎯 Principais Funcionalidades

1. **Detecção e Coleta Inteligente no YouTube (SPA & Dynamic DOM)**:
   - Resultados de busca (canais, vídeos, playlists, shorts).
   - Página do canal (`/@handle` e `/channel/UC...`).
   - Página de exibição de vídeos (`/watch` - seção do canal proprietário).
   - Prevenção atômica de duplicidades via `channel_id UNIQUE` no PostgreSQL.
2. **Sistema de Sessões de Trabalho (Work Sessions)**:
   - Início manual obrigatório: `○ COLETA PARADA` $\rightarrow$ `[ 🚀 INICIAR COLETA ]`.
   - Cronômetro em tempo real sincronizado com timestamps do servidor.
   - Botões `[ ⏸ PAUSAR ]`, `[ ▶ RETOMAR ]` e `[ ⏹ FINALIZAR ]`.
   - **Tempo pausado NÃO é contabilizado como horas trabalhadas**.
3. **Sistema de Ciclos & Metas Matemáticas**:
   - **Ciclo 8 Horas**: Meta de 160 canais / 8h $\rightarrow$ 20,0 canais/h.
   - **Ciclo 6 Horas**: Meta de 160 canais / 6h $\rightarrow$ 26,7 canais/h (cálculo exato).
   - **Ciclo Personalizado**: Definição livre de meta e horas.
   - **Ritmo Atual vs. Ritmo Necessário**: Cálculo dinâmico para atingir a meta no tempo restante.
4. **Ranking da Equipe por Horas Trabalhadas**:
   - Classificação **estritamente ordenada por horas ativas trabalhadas** (`active_seconds DESC`).
   - Filtros por período: `Hoje`, `Esta Semana`, `Este Mês`.
5. **Dashboard Web Central (`/dashboard`)**:
   - 📊 **Visão Geral**: KPIs da equipe em tempo real e cards ao vivo de cada membro com cronômetros e ritmos.
   - 🏆 **Ranking de Horas**: Tabela de classificação com pódio.
   - 📜 **Histórico**: Relatório detalhado de sessões por data e usuário.
   - 📺 **Canais Coletados**: Lista de canais com busca e exportação em CSV.
   - ⚙️ **Configurações**: Gerenciamento de metas diárias e presets.

---

## 🏗️ Estrutura do Projeto

```
youtube-prospector/
├── backend/
│   ├── config/
│   │   └── settings.py          # Configurações gerais (PostgreSQL, JWT, CORS, URLs)
│   ├── database/
│   │   ├── connection.py        # Conexão SQLAlchemy (PostgreSQL / SQLite)
│   │   └── models.py            # User, Channel, CollectionEvent, WorkSession, WorkSessionEvent
│   ├── routes/
│   │   ├── auth.py              # /auth/login, /auth/me, /auth/register
│   │   ├── channels.py          # /channels/check, /channels, /channels/bulk, /channels/list
│   │   ├── stats.py             # /stats/me, /stats/team
│   │   └── work_sessions.py     # /work-sessions/start, pause, resume, finish, ranking, team/status
│   ├── schemas/                 # Pydantic schemas (Channel, Auth, Stats, WorkSession)
│   ├── security/
│   │   └── auth.py              # JWT, hash bcrypt e get_current_user
│   ├── services/
│   │   ├── channel_service.py   # Lógica atômica de concorrência e bulk check
│   │   └── work_session_service.py # Lógica de sessões, ritmo de coleta e ranking
│   ├── templates/
│   │   └── dashboard.html       # Painel web moderno com abas e ranking
│   ├── seed.py                  # Script para popular usuários de teste
│   ├── main.py                  # FastAPI app com CORS, /health, /dashboard e routers
│   ├── requirements.txt
│   └── .env.example
├── extension/
│   ├── manifest.json            # Chrome Manifest V3
│   ├── background.js            # Service Worker
│   ├── content.js               # Injeção no DOM, observer e eventos
│   ├── youtube-parser.js        # Extração de canais, handles (@handle) e Channel IDs
│   ├── api.js                   # Cliente HTTP autenticado (Bearer Token + Work Sessions)
│   ├── auth.js                  # Gerenciador de sessão e storage local
│   ├── cache.js                 # Cache com expiração (TTL) de Channel IDs
│   ├── popup/
│   │   ├── popup.html           # Interface do Popup com painel de produtividade
│   │   ├── popup.css            # Estilos dark theme modernos
│   │   └── popup.js             # Lógica do timer, ciclos, coletas e status
│   ├── styles/
│   │   └── youtube-overlay.css  # Badges e barra flutuante no YouTube
│   └── icons/                   # Ícones da extensão (16, 48, 128)
└── tests/
    ├── test_api.py              # Testes automatizados de API e concorrência
    └── test_work_sessions.py    # Testes de sessões, ciclos e ranking de horas
```

---

## 🚀 Como Executar

### 1. Iniciar o Backend
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
- **Dashboard Web**: `http://localhost:8000/dashboard`
- **Swagger Docs**: `http://localhost:8000/docs`

### 2. Usuários de Teste (Senha: `123`)
- `carlos@prospector.com`
- `maria@prospector.com`
- `joao@prospector.com`
- `ana@prospector.com`

### 3. Instalar a Extensão no Chrome
1. Acesse `chrome://extensions/` no Google Chrome.
2. Ative o **"Modo do desenvolvedor"**.
3. Clique em **"Carregar sem compactação"** e selecione a pasta:  
   `c:\Users\PICHAU\Desktop\extensao\extension`.
4. Abra o popup, faça login, selecione um ciclo e inicie sua sessão de trabalho!
