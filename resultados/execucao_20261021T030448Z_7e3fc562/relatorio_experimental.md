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
| C1 | Monolítica | 3 | 540 | 20.828 | 26.794 | 28.382 | 31.696 | 48.01 | 100.00% |
| C1 | Multicamada | 3 | 540 | 23.187 | 28.910 | 31.709 | 34.344 | 43.13 | 100.00% |
| C2 | Multicamada | 3 | 540 | 23.808 | 29.088 | 35.086 | 52.016 | 42.00 | 100.00% |
| C2 | Monolítica | 3 | 540 | 21.305 | 27.266 | 30.678 | 45.206 | 46.94 | 100.00% |
| C3 | Monolítica | 3 | 540 | 20.873 | 24.337 | 27.574 | 36.028 | 47.91 | 100.00% |
| C3 | Multicamada | 3 | 540 | 24.157 | 25.968 | 27.742 | 30.608 | 41.40 | 100.00% |
| C4 | Multicamada | 3 | 540 | 34.426 | 39.553 | 45.084 | 56.203 | 29.05 | 100.00% |
| C4 | Monolítica | 3 | 540 | 30.756 | 38.421 | 47.631 | 79.738 | 32.51 | 100.00% |

## Comparação observada

- **C1:** média multicamada 11.33% maior que a monolítica; P99 observado de 31.709 ms contra 28.382 ms. Quadros acima do orçamento: 100.00% contra 100.00%.
- **C2:** média multicamada 11.75% maior que a monolítica; P99 observado de 35.086 ms contra 30.678 ms. Quadros acima do orçamento: 100.00% contra 100.00%.
- **C3:** média multicamada 15.73% maior que a monolítica; P99 observado de 27.742 ms contra 27.574 ms. Quadros acima do orçamento: 100.00% contra 100.00%.
- **C4:** média multicamada 11.93% maior que a monolítica; P99 observado de 45.084 ms contra 47.631 ms. Quadros acima do orçamento: 100.00% contra 100.00%.

## Limites da interpretação

Os números descrevem somente a carga, o ambiente e a duração registrados. P95, P99 e máximo observado não são WCET nem garantias de prazo; zero violações observadas não assegura ausência futura. A separação em camadas, por si só, não demonstra melhor previsibilidade. Não foram avaliados escalonamento de tempo real, tolerância a falhas ou certificação aeronáutica. O aplicativo é uma demonstração acadêmica.

Os testes usam a mesma sessão de processo/contexto, liberando recursos entre execuções; caches do driver, temperatura, frequência da GPU e atividade do sistema podem influenciar os resultados. Alternar a ordem reduz um possível viés, mas não substitui controle ambiental ou estudo estatístico de significância.

## Arquivos para auditoria

- `amostras_frames.csv`: uma linha por quadro, com configuração, estratégia e repetição.
- `amostras_recursos.csv`: RSS e intervalos de CPU medidos fora da duração do quadro.
- `resultados_benchmark.csv`: estatísticas de cada repetição; `resumo_agregado.csv`: agregados.
- `resumo.json` e `metadados.json`: parâmetros, versões e identificação do ambiente OpenGL.
- `graficos/`: FPS, médias, distribuição e recursos; `capturas/`: último quadro da primeira repetição.
