# Correspondência com o enunciado

O projeto preserva o **Eixo 1 — Aviação e Sistemas Críticos**. A versão AERIS adapta a composição de subsistemas para uma estação terrestre de inspeção ambiental por drone, com incêndios, terreno e navegação sintéticos. O artigo de Barladian et al. trata de cockpit embarcado e JetOS; a implementação desta pasta executa em um computador convencional, com outra missão e outro algoritmo de representação 3D.

O enunciado apresenta uma particularidade: os artigos indicados ao Eixo 1 tratam de composição/certificação, mas a etapa de algoritmo central menciona **projeção, ordenação e rasterização de Gaussianas**. A implementação contempla os dois pontos explicitamente.

| Exigência | Evidência disponível |
|---|---|
| Aplicação gráfica interativa | `main.py`, com GLFW/ModernGL, controles de teclado, mouse e ajuda |
| Etapa 1: fundamentação bibliográfica | `revisao_bibliografica.md`, com três fontes primárias verificadas |
| Adaptação para outro contexto | Missão de estação de drone para inspeção de incêndios, documentada no artigo |
| Etapa 2: dados, geometria e câmera | `simulador.py`, gerador procedural em `gaussianas.py`, buffers persistentes e câmera orbital |
| Etapa 3: projeção de Gaussianas | `projetar_gaussianas`: transformação da covariância com Jacobiana perspectiva |
| Etapa 3: ordenação | Ordem global estável por profundidade; desempate por ID; cache comparado ao cálculo integral |
| Etapa 3: rasterização | Quads instanciados, suporte elíptico, exponencial Gaussiana e alpha pré-multiplicado |
| Estruturas e otimização | Arrays NumPy vetorizados, descarte de invisíveis, cache estático e buffers expansíveis |
| Etapa 4: complexidade e resolução | C1–C4, quantidade de Gaussianas independente, 720p e 1080p offscreen exatos |
| Métricas de desempenho | Média, dispersão, mediana, P95/P99, máximo amostral, FPS, CPU e RSS |
| Qualidade visual | Capturas de ambos os modos e testes numéricos de pixels com OpenGL real |
| Dados para análise | CSV por frame e repetição, JSON de parâmetros e ambiente, quatro gráficos |
| Artigo científico em duas colunas | `artigo/main.tex`, usando a classe IEEEtran e resultados desta execução |
| Demonstração e apresentação | `roteiro_apresentacao.md`, guia de cinco minutos; aplicação e captura disponíveis |

## Pontos para a entrega

O artigo é editável e já contém a metodologia, as tabelas da execução validada, figuras, análise, limitações e referências. Revise os dados institucionais que a disciplina exigir e a redação dos autores antes da submissão.

O PDF final foi compilado e revisado visualmente em **quatro páginas, duas colunas**, em `../output/pdf/AERIS_artigo.pdf`. As fontes completas para edição e importação no Overleaf estão em `artigo-fontes.zip`.

A numeração C1–C4, suas quantidades e as resoluções são escolhas experimentais do projeto, e não uma tabela prescrita no PDF. O aplicativo utiliza OpenGL 3.3 convencional; seus FBOs não implementam o particionamento de um sistema operacional de tempo real. A cena procedural não utiliza reconstrução neural ou dados geográficos reais.

A coleta registra latência CPU+GPU sincronizada. Ela não estabelece pior caso de execução, certificação ou superioridade temporal automática da composição multicamada. As conclusões no artigo e no relatório seguem os valores efetivamente medidos.
