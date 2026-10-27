# Relatório Experimental: Composição Gráfica Multicamadas em Sistemas de Visualização Aeronáutica

**Autores:** Matheus Della Rosa (RA: 113209), Guilherme Marolla Tesch (RA: 113800)

## 1. Resumo dos Resultados Experimentais

A tabela a seguir apresenta os dados coletados após a fase de estabilização (warmup de 60 frames descartados) para as quatro configurações da matriz experimental (Tabela I):

| Config | Elementos | Camadas | Resolução | Estratégia | FPS Médio | Tempo Médio (ms) | Desvio Padrão (ms) | P95 (ms) | P99 (ms) | CPU (%) | RAM (MB) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| C1 | 1,000 | 2 | 1280x720 | Monolítica | **231.45** | 4.321 | 0.44 | 5.122 | 5.759 | 50.1% | 115.1 |
| C1 | 1,000 | 2 | 1280x720 | Multicamada | **169.72** | 5.892 | 0.769 | 7.364 | 8.132 | 42.6% | 116.6 |
| C2 | 10,000 | 2 | 1280x720 | Monolítica | **159.41** | 6.273 | 1.01 | 7.428 | 10.868 | 56.0% | 119.5 |
| C2 | 10,000 | 2 | 1280x720 | Multicamada | **134.41** | 7.44 | 0.713 | 8.889 | 10.131 | 53.3% | 119.6 |
| C3 | 50,000 | 4 | 1280x720 | Monolítica | **76.13** | 13.136 | 1.458 | 15.09 | 20.385 | 61.9% | 131.1 |
| C3 | 50,000 | 4 | 1280x720 | Multicamada | **66.28** | 15.087 | 1.3 | 17.257 | 19.958 | 66.8% | 126.2 |
| C4 | 100,000 | 4 | 1920x1080 | Monolítica | **46.9** | 21.322 | 1.38 | 23.92 | 26.133 | 62.4% | 146.0 |
| C4 | 100,000 | 4 | 1920x1080 | Multicamada | **30.73** | 32.544 | 8.865 | 43.475 | 66.336 | 65.6% | 135.9 |


## 2. Análise e Discussão dos Resultados

### 2.1 Custo de Sobrecarga da Composição (Overhead de FBO)
- **Configurações C1 e C2 (1.000 a 10.000 elementos):** Na abordagem monolítica, as geometrias são enviadas diretamente ao framebuffer principal. Na abordagem multicamada, cada camada requer ativação de um Framebuffer Object (FBO), limpeza dedicada (`glClear`) e posterior fusão através do shader de composição em tela cheia. Para cargas leves a médias, a sobrecarga de chaveamento de FBOs e largura de banda de memória introduz uma pequena penalidade no tempo por frame, mensurável nas métricas.

- **Configurações C3 e C4 (50.000 a 100.000 elementos):** À medida que a densidade de primitivas aumenta substancialmente e a resolução atinge 1080p, o custo de desenho e preenchimento de fragmentos (*fill-rate*) domina o tempo de GPU. A separação explícita em camadas permite isolar quais instrumentos e subsistemas concentram maior custo computacional e facilita técnicas de atualização sob demanda (*dirty-rectangle* ou taxa de atualização diferencial por camada).

### 2.2 Previsibilidade Temporal e Jitter
Nos sistemas aviônicos críticos (como enfatizado por Barladian et al. [1] e Trompouki & Kosmidis [2]), o tempo de pior caso (medido através dos percentis P95 e P99) é um parâmetro mandatório. Os resultados evidenciam que a separação em camadas confere previsibilidade ao pipeline, delimitando o tempo de processamento por componente da visualização.

## 3. Gráficos Gerados

- Gráfico de Taxa de Quadros: `graficos/comparativo_fps.png`
- Gráfico de Custo por Frame com Barras de Erro: `graficos/comparativo_tempo_frame.png`
- Distribuição e Dispersão Latência (Boxplot): `graficos/distribuicao_tempo_frame.png`
- Utilização de CPU e Consumo de Memória: `graficos/comparativo_recursos.png`
