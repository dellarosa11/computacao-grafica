# Relatório experimental de composição gráfica

## Método

Latência CPU + GPU em framebuffer offscreen RGBA8. Cada quadro inclui construção da geometria, envio dos comandos e `ctx.finish()`; não inclui simulação, coleta de recursos, PNG, eventos, troca de buffers ou V-Sync. Não corresponde ao tempo exclusivo da GPU nem à latência de apresentação na tela.

Aquecimento por execução: 60 quadros; coleta por repetição: 180 quadros; repetições: 3; semente: 42. As estratégias recebem os mesmos snapshots com passo fixo de 1/60 s. A ordem alterna entre repetições.

Cenário: incendio; cena 3D: 6000 gaussianas. A contagem de gaussianas é independente da carga sintética de retângulos dos presets.

FPS é 1000 dividido pela média dos tempos. Percentis usam interpolação linear. Os agregados reúnem todas as amostras; o CSV por repetição permite examinar a variação entre execuções. As barras de erro mostram o desvio padrão entre médias das repetições, não um intervalo de confiança.

CPU é a razão entre segundos de CPU do processo e tempo de parede de toda a coleta; pode exceder 100% em vários núcleos. O arquivo de recursos traz RSS amostrada e CPU em intervalos de pelo menos 100 ms quando disponíveis. RSS mede o processo completo, incluindo Python e caches do driver; não mede VRAM ou memória exclusiva de uma estratégia.

## Resultados agregados

| Config | Estratégia | Repetições | Quadros | Média (ms) | P95 (ms) | P99 (ms) | Máximo observado (ms) | FPS | Fora de 16,67 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 | Monolítica | 3 | 540 | 6.027 | 9.077 | 11.658 | 15.022 | 165.92 | 0.00% |
| C1 | Multicamada | 3 | 540 | 6.350 | 9.788 | 13.834 | 27.267 | 157.48 | 0.37% |
| C2 | Multicamada | 3 | 540 | 7.179 | 12.417 | 14.228 | 15.478 | 139.29 | 0.00% |
| C2 | Monolítica | 3 | 540 | 7.230 | 10.735 | 13.490 | 15.838 | 138.31 | 0.00% |
| C3 | Monolítica | 3 | 540 | 11.258 | 13.091 | 15.944 | 19.171 | 88.83 | 0.93% |
| C3 | Multicamada | 3 | 540 | 11.647 | 15.154 | 19.114 | 24.040 | 85.86 | 3.89% |
| C4 | Multicamada | 3 | 540 | 16.876 | 18.718 | 24.632 | 25.685 | 59.26 | 46.11% |
| C4 | Monolítica | 3 | 540 | 16.757 | 19.493 | 21.229 | 26.292 | 59.67 | 35.93% |

## Comparação observada

- **C1:** média multicamada 5.36% maior que a monolítica; P99 observado de 13.834 ms contra 11.658 ms. Quadros acima do orçamento: 0.37% contra 0.00%.
- **C2:** média multicamada 0.71% menor que a monolítica; P99 observado de 14.228 ms contra 13.490 ms. Quadros acima do orçamento: 0.00% contra 0.00%.
- **C3:** média multicamada 3.46% maior que a monolítica; P99 observado de 19.114 ms contra 15.944 ms. Quadros acima do orçamento: 3.89% contra 0.93%.
- **C4:** média multicamada 0.71% maior que a monolítica; P99 observado de 24.632 ms contra 21.229 ms. Quadros acima do orçamento: 46.11% contra 35.93%.

## Limites da interpretação

Os números descrevem somente a carga, o ambiente e a duração registrados. P95, P99 e máximo observado não são WCET nem garantias de prazo; zero violações observadas não assegura ausência futura. A separação em camadas, por si só, não demonstra melhor previsibilidade. Não foram avaliados escalonamento de tempo real, tolerância a falhas ou certificação aeronáutica. O aplicativo é uma demonstração acadêmica.

Os testes usam a mesma sessão de processo/contexto, liberando recursos entre execuções; caches do driver, temperatura, frequência da GPU e atividade do sistema podem influenciar os resultados. Alternar a ordem reduz um possível viés, mas não substitui controle ambiental ou estudo estatístico de significância.

## Arquivos para auditoria

- `amostras_frames.csv`: uma linha por quadro, com configuração, estratégia e repetição.
- `amostras_recursos.csv`: RSS e intervalos de CPU medidos fora da duração do quadro.
- `resultados_benchmark.csv`: estatísticas de cada repetição; `resumo_agregado.csv`: agregados.
- `resumo.json` e `metadados.json`: parâmetros, versões e identificação do ambiente OpenGL.
- `graficos/`: FPS, médias, distribuição e recursos; `capturas/`: último quadro da primeira repetição.
