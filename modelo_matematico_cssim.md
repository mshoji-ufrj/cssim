# Montagem do modelo matemático no CSSIM

Este documento revisa, de forma alinhada ao notebook [cssim_first_order.ipynb](cssim_first_order.ipynb), como o CSSIM transforma um diagrama de blocos em um modelo matemático simulável. O foco é o exemplo de sistema de primeira ordem definido em [diagrams/first_order_step.json](diagrams/first_order_step.json).

---

## Visão geral

O CSSIM transforma um diagrama de blocos em um problema dinâmico da forma

$$
\dot{\mathbf{x}}(t) = f\bigl(t, \mathbf{x}(t)\bigr),
$$

em que:

- $\mathbf{x}(t)$ é o vetor global de estados internos dos blocos dinâmicos;
- os blocos algébricos são reunidos em um sistema linear;
- as entradas externas são convertidas em funções do tempo;
- as saídas são reconstruídas a partir das interconexões do diagrama.

No notebook, o fluxo é apresentado em 10 etapas:

1. leitura do diagrama em JSON;
2. criação do grafo do diagrama;
3. resolução dos parâmetros simbólicos;
4. categorização dos blocos;
5. conversão da função de transferência para espaço de estados;
6. montagem do modelo matemático do sistema;
7. geração dos sinais de entrada;
8. execução da simulação;
9. visualização dos resultados;
10. incorporação ao Jupyter Notebook.

As funções principais envolvidas nesse fluxo são:

- `load_json(...)`
- `build_graph(...)`
- `set_parameters(...)`
- `resolve_param(...)`
- `categorize_blocks(...)`
- `tf_to_ss(...)`
- `build_solver(...)`
- `compute_rhs(...)`
- `generate_input_signal(...)`
- `run_simulation(...)`
- `plot_signals(...)`
- `open_gui(...)`

---

## Contexto comum do notebook

Antes das 10 etapas, o notebook cria um contexto comum reutilizado ao longo da análise:

- define o símbolo de Laplace $s$;
- define `diagram_path = "diagrams/first_order_step.json"`;
- fixa $T = 1$;
- monta `param_values = {"T": 1}`;
- registra os parâmetros com `set_parameters(param_values)`;
- lê o diagrama com `data = load_json(diagram_path)`.

Esse preparo é importante porque, nas etapas seguintes, o notebook passa a analisar o mesmo diagrama sempre com a mesma parametrização.

No exemplo estudado, a malha fechada é descrita por

$$
E(s)=R(s)-C(s),
\qquad
G(s)=\frac{1}{Ts},
\qquad
\frac{C(s)}{R(s)}=\frac{1}{Ts+1}.
$$

---

## Etapa 1 — Leitura do diagrama em JSON com `load_json(...)`

A função `load_json(path)` lê o arquivo JSON e devolve uma estrutura com, no mínimo:

- `blocks`: lista de blocos;
- `connections`: lista de conexões;
- `sim_time`: tempo de simulação;
- `step_size`: passo de integração.

No notebook, a chamada é feita com:

```python
data = load_json("diagrams/first_order_step.json")
```

O arquivo lido contém:

- 4 blocos;
- 5 conexões;
- um bloco de entrada do tipo `step`;
- um bloco de operação com sinais `+` e `-`;
- um bloco de função de transferência com numerador `1` e denominador `T*s`;
- um bloco de saída.

Matematicamente, essa etapa ainda não resolve a dinâmica. Ela apenas identifica a estrutura que depois será convertida em equações.

Para o exemplo, o notebook explicita as relações:

$$
R(s)=\frac{1}{s},
\qquad
E(s)=R(s)-C(s),
\qquad
G(s)=\frac{1}{Ts},
\qquad
C(s)=G(s)E(s).
$$

---

## Etapa 2 — Criação do grafo com `build_graph(...)`

A função `build_graph(data)` constrói um grafo direcionado $G$, no qual:

- cada nó representa um bloco;
- cada aresta representa fluxo de sinal;
- conectores intermediários são colapsados para preservar a relação bloco-a-bloco.

No exemplo do notebook, os nós identificados são:

- `Block0`: entrada;
- `Block1`: operação;
- `Block2`: função de transferência;
- `Block3`: saída.

As arestas mostradas pelo notebook são:

$$
\text{Block0} \to \text{Block1},
\qquad
\text{Block1} \to \text{Block2},
\qquad
\text{Block2} \to \text{Block3},
\qquad
\text{Block2} \to \text{Block1}.
$$

Logo, a realimentação negativa fica explícita no grafo: a saída do bloco dinâmico retorna ao somador.

Essa estrutura computacional é a base para determinar:

- predecessores de cada bloco;
- origem dos sinais de entrada;
- realimentações;
- ordem de montagem das equações algébricas e diferenciais.

---

## Etapa 3 — Resolução dos parâmetros com `set_parameters(...)` e `resolve_param(...)`

O CSSIM permite que parâmetros do diagrama sejam escritos simbolicamente, por exemplo:

- `T`
- `K`
- `2*zeta*wn`
- `wn**2`

No notebook, o parâmetro relevante é a constante de tempo $T$, definida por

$$
T = 1.
$$

A função `set_parameters(...)` registra esse valor, e `resolve_param(...)` substitui a expressão simbólica pelo valor numérico correspondente.

No exemplo:

$$
\texttt{resolve\_param("T")} = 1.0.
$$

Assim, o denominador simbólico do bloco

$$
T s
$$

passa, numericamente, a ser interpretado como

$$
1.0\,s.
$$

Essa etapa é necessária porque a conversão para espaço de estados exige coeficientes numéricos.

---

## Etapa 4 — Categorização dos blocos com `categorize_blocks(...)`

A função `categorize_blocks(data, G, param_values)` percorre os blocos e os separa em grupos funcionais.

No notebook, a saída dessa etapa é:

- `input_blocks = ['Block0']`
- `tf_blocks = ['Block2']`
- `static_blocks = ['Block1']`
- `pid_blocks = []`
- `output_blocks = ['Block3']`
- `total_states = 1`

Isso significa que:

- o bloco de entrada representa a referência $r(t)$;
- o bloco estático representa o somador do erro;
- o bloco dinâmico representa $G(s)=\frac{1}{Ts}$;
- o sistema total possui apenas um estado.

De forma geral, essa etapa separa:

- blocos de entrada;
- blocos de função de transferência;
- blocos algébricos, como somadores e ganhos;
- blocos PID;
- blocos de saída.

Depois disso, o CSSIM concatena todos os estados dos blocos dinâmicos em um vetor global

$$
\mathbf{x}(t) = \bigl(x_1(t), x_2(t), \ldots, x_n(t)\bigr)^\top.
$$

No exemplo do notebook, esse vetor tem dimensão 1.

---

## Etapa 5 — Conversão da função de transferência com `tf_to_ss(...)`

A função `tf_to_ss(num, den, param_values=None)` recebe o numerador e o denominador de um bloco dinâmico e produz uma realização em espaço de estados.

Para um bloco genérico

$$
G(s)=\frac{N(s)}{D(s)},
$$

o CSSIM constrói matrizes $(\mathbf{A},\mathbf{B},\mathbf{C},\mathbf{D})$ tais que

$$
G(s)=\mathbf{C}(s\mathbf{I}-\mathbf{A})^{-1}\mathbf{B} + \mathbf{D}.
$$

No notebook, a chamada é feita com:

```python
A_tf, B_tf, C_tf, D_tf = tf_to_ss("1", "T*s", param_values={"T": 1})
```

Como $T=1$, o resultado numérico mostrado é:

$$
\mathbf{A} = [0],
\qquad
\mathbf{B} = [1],
\qquad
\mathbf{C} = [1],
\qquad
\mathbf{D} = 0.
$$

Em forma simbólica, antes da substituição $T=1$, a interpretação é

$$
\dot{x}(t)=e(t),
\qquad
c(t)=\frac{1}{T}x(t).
$$

Portanto, o estado $x(t)$ funciona como a integral do erro, e a saída é uma versão escalada desse estado.

---

## Etapa 6 — Montagem do modelo matemático com `build_solver(...)` e `compute_rhs(...)`

Essa é a etapa central da formulação do sistema.

Antes de olhar o caso particular do notebook, vale entender a ideia geral do que o CSSIM faz nessa etapa.

Quando o diagrama possui blocos dinâmicos e blocos algébricos interligados, o problema natural não aparece imediatamente como uma única EDO explícita. Primeiro, o CSSIM separa as variáveis em dois grupos:

- **estados dinâmicos** $\mathbf{x}(t)$, associados aos blocos que têm memória, como funções de transferência e controladores com integradores;
- **saídas algébricas internas** $\mathbf{y}(t)$, associadas aos sinais produzidos por somadores, ganhos, saídas de blocos dinâmicos e outros blocos que dependem instantaneamente de entradas e estados.

Também existe o conjunto das **entradas externas** $\mathbf{u}(t)$, geradas pelos blocos de entrada do diagrama.

De forma genérica, o CSSIM monta primeiro um sistema algébrico do tipo

$$
\mathbf{M}\,\mathbf{y}(t)=\mathbf{H}\,\mathbf{x}(t)+\mathbf{u}(t),
$$

em que:

- $\mathbf{y}(t)$ reúne as saídas internas dos blocos relevantes do diagrama;
- $\mathbf{x}(t)$ é o vetor global de estados;
- $\mathbf{u}(t)$ reúne os sinais externos aplicados ao diagrama;
- $\mathbf{M}$ descreve como as saídas algébricas dependem umas das outras;
- $\mathbf{H}$ projeta a contribuição dos estados internos sobre as variáveis algébricas;
- $\mathbf{u}(t)$ representa diretamente a contribuição das entradas externas na forma compacta adotada aqui.

Se $\mathbf{M}$ é inversível, então o sistema algébrico pode ser resolvido como

$$
\mathbf{y}(t)=\mathbf{M}^{-1}\bigl(\mathbf{H}\,\mathbf{x}(t)+\mathbf{u}(t)\bigr).
$$

Em seguida, o CSSIM monta a parte dinâmica. De forma genérica, a derivada dos estados pode ser escrita como

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}\,\mathbf{y}(t)+\mathbf{E}\,\mathbf{u}(t).
$$

Essa equação diz que a evolução dos estados pode depender:

- do próprio estado atual $\mathbf{x}(t)$;
- dos sinais algébricos internos $\mathbf{y}(t)$;
- das entradas externas $\mathbf{u}(t)$.

Substituindo a expressão de $\mathbf{y}(t)$, o sistema fica totalmente em função de $\mathbf{x}(t)$ e de $\mathbf{u}(t)$:

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}\,\mathbf{M}^{-1}\bigl(\mathbf{H}\,\mathbf{x}(t)+\mathbf{u}(t)\bigr)+\mathbf{E}\,\mathbf{u}(t).
$$

Agrupando os termos,

$$
\dot{\mathbf{x}}(t)=\bigl(\mathbf{A}+\mathbf{B}\,\mathbf{M}^{-1}\mathbf{H}\bigr)\mathbf{x}(t)+\bigl(\mathbf{B}\,\mathbf{M}^{-1}+\mathbf{E}\bigr)\mathbf{u}(t).
$$

Esse é o ponto principal da etapa 6: o CSSIM pega uma interconexão de blocos, resolve as dependências algébricas internas e a transforma em uma EDO explícita utilizável pelo integrador numérico.

### Sistema algébrico montado por `build_solver(...)`

A função

```python
build_solver(input_blocks, static_blocks, tf_blocks, pid_blocks, total_states)
```

produz, no notebook:

- `output_ids = ['Block1', 'Block2']`
- `output_index = {'Block1': 0, 'Block2': 1}`
- `M_inv = [[1, -1], [0, 1]]`
- `input_map = {0: [('Block0', 1.0)], 1: []}`
- `H_matrix = [[0], [1]]`

Interpretando esses objetos com mais calma:

- `output_ids` indica quais sinais internos foram escolhidos para compor o vetor algébrico $\mathbf{y}(t)$;
- `output_index` apenas associa cada bloco à sua posição dentro desse vetor;
- `M_inv` é a inversa da matriz que resolve o acoplamento algébrico entre esses sinais;
- `input_map` informa quais entradas externas contribuem diretamente para cada equação algébrica;
- `H_matrix` informa como os estados internos contribuem para essas mesmas equações e corresponde, no código, à matriz $\mathbf{H}$ da formulação matemática.

Como `Block1` é o somador e `Block2` é o bloco dinâmico, o vetor algébrico pode ser escrito como

$$
\mathbf{y}(t)=\bigl(e(t), c(t)\bigr)^\top.
$$

Isso é importante: nessa etapa o CSSIM ainda não está integrando nada. Ele está apenas respondendo à pergunta:

> dado um estado atual $\mathbf{x}(t)$ e um valor atual da entrada $r(t)$, quais são instantaneamente os sinais internos do diagrama?

No exemplo, as equações algébricas são

$$
e(t)=r(t)-c(t),
$$

$$
c(t)=\frac{1}{T}x(t).
$$

Em forma compacta, isso pode ser escrito como

$$
\mathbf{M}\,\mathbf{y}(t)=\mathbf{b}(t),
$$

com

$$
\mathbf{M} = \begin{pmatrix} 1 & 1 \\ 0 & 1 \end{pmatrix},
$$

$$
\mathbf{y}(t)=\bigl(e(t), c(t)\bigr)^\top,
\qquad
\mathbf{b}(t)=\bigl(r(t), \tfrac{1}{T}x(t)\bigr)^\top.
$$

Se o preview continuar sem renderizar a matriz $\mathbf{M}$, a forma por componentes é exatamente:

$$
e(t)+c(t)=r(t),
\qquad
c(t)=\frac{1}{T}x(t).
$$

Como o notebook já fornece $\mathbf{M}^{-1}$, a solução pode ser escrita diretamente como

$$
\mathbf{y}(t)=\mathbf{M}^{-1}\bigl(\mathbf{C}_{\text{alg}}\mathbf{x}(t)+\mathbf{u}_{\text{ext}}(t)\bigr),
$$

com

$$
\mathbf{M}^{-1} = \begin{pmatrix} 1 & -1 \\ 0 & 1 \end{pmatrix}.
$$

Em outras palavras, o `build_solver(...)` monta a parte de **fechamento instantâneo da malha**. Ele resolve o somador, a realimentação e as relações diretas entre sinais sem ainda integrar a dinâmica.

### Dinâmica montada por `compute_rhs(...)`

A função `compute_rhs(...)` constrói a função do lado direito da EDO global,

$$
\dot{\mathbf{x}}(t)=f(t,\mathbf{x}).
$$

Agora aparece a segunda metade da etapa 6. Depois de o sistema algébrico informar quanto vale cada sinal interno, o CSSIM usa essas informações para calcular a derivada dos estados. Em linguagem prática:

1. avalia a entrada externa no instante $t$;
2. usa $\mathbf{x}(t)$ e a entrada para resolver o sistema algébrico;
3. obtém os sinais internos, como erro, saída de somadores e saídas de blocos;
4. usa esses sinais para calcular $\dot{\mathbf{x}}(t)$.

Portanto, `compute_rhs(...)` encapsula exatamente a função que o integrador numérico precisa consultar repetidamente.

### Aplicação genérica da etapa 6

Juntando as duas partes, a etapa 6 pode ser resumida assim:

1. o diagrama é convertido em relações algébricas entre sinais internos;
2. essas relações são organizadas na forma matricial $\mathbf{M}\,\mathbf{y} = \mathbf{H}\,\mathbf{x} + \mathbf{u}$;
3. o vetor algébrico é resolvido como $\mathbf{y} = \mathbf{M}^{-1}(\mathbf{H}\,\mathbf{x} + \mathbf{u})$;
4. a dinâmica dos blocos com estado é escrita como $\dot{\mathbf{x}} = \mathbf{A}\,\mathbf{x} + \mathbf{B}\,\mathbf{y} + \mathbf{E}\,\mathbf{u}$;
5. a substituição de $\mathbf{y}$ produz uma única EDO explícita.

Isso significa que o CSSIM transforma um diagrama de blocos com realimentações em um modelo matemático pronto para simulação, sem que o usuário precise montar manualmente as equações do sistema inteiro.

### Aplicação ao exemplo de primeira ordem

No sistema do notebook, existe apenas um estado interno, associado ao bloco de função de transferência $G(s)=\frac{1}{Ts}$. Portanto,

$$
\mathbf{x}(t) \in \mathbb{R}.
$$

O vetor algébrico escolhido pelo CSSIM reúne dois sinais:

$$
\mathbf{y}(t)=\bigl(e(t),c(t)\bigr)^\top,
$$

onde:

- $e(t)$ é a saída do somador, isto é, o erro;
- $c(t)$ é a saída do bloco dinâmico, isto é, a saída da planta em malha fechada.

Como a entrada externa é a referência, podemos escrever

$$
\mathbf{u}(t)=r(t).
$$

As relações estruturais do diagrama são:

$$
e(t)=r(t)-c(t),
$$

$$
c(t)=\frac{1}{T}x(t).
$$

A primeira equação vem do somador com sinais `+` e `-`; a segunda vem da realização em espaço de estados do integrador $\frac{1}{Ts}$.

Escrevendo essas relações em forma de sistema,

$$
\begin{aligned}
e(t) + c(t) &= r(t), \\
c(t) &= \frac{1}{T}x(t).
\end{aligned}
$$

Ou seja,

$$
\mathbf{M}\,\mathbf{y}(t)=\mathbf{H}\,\mathbf{x}(t)+r(t).
$$

Se quisermos apenas identificar as matrizes envolvidas, então elas são

$$
\mathbf{M} = \begin{pmatrix} 1 & 1 \\ 0 & 1 \end{pmatrix},
\qquad
\mathbf{H} = \begin{pmatrix} 0 \\ \frac{1}{T} \end{pmatrix}.
$$

Resolvendo esse sistema, o CSSIM obtém instantaneamente $e(t)$ e $c(t)$ para qualquer valor atual de $x(t)$ e de $r(t)$.

Na parte dinâmica, o bloco $\frac{1}{Ts}$ foi realizado de modo que seu estado obedece

$$
\dot{x}(t)=e(t).
$$

Esse ponto é essencial: o estado cresce ou decresce de acordo com o erro aplicado à entrada do integrador. Como o sistema algébrico já mostrou que

$$
e(t)=r(t)-\frac{1}{T}x(t),
$$

segue imediatamente que

$$
\dot{x}(t)=r(t)-\frac{1}{T}x(t).
$$

Essa é a EDO final montada pelo CSSIM para o exemplo. Ela já está na forma explícita usada pelo integrador numérico.

Se quisermos escrever o resultado em termos da saída $c(t)$, basta usar

$$
c(t)=\frac{1}{T}x(t).
$$

Derivando,

$$
\dot{c}(t)=\frac{1}{T}\dot{x}(t).
$$

Substituindo a expressão de $\dot{x}(t)$,

$$
\dot{c}(t)=\frac{1}{T}r(t)-\frac{1}{T}c(t),
$$

ou, equivalentemente,

$$
T\dot{c}(t)+c(t)=r(t).
$$

Portanto, no exemplo de primeira ordem, a etapa 6 faz exatamente o seguinte:

- resolve a malha algébrica para descobrir o erro $e(t)$;
- usa esse erro para determinar a derivada do estado interno;
- elimina as variáveis intermediárias e produz a equação diferencial final da malha fechada.

No exemplo, como

$$
\dot{x}(t)=e(t)
$$

e

$$
e(t)=r(t)-\frac{1}{T}x(t),
$$

segue que

$$
\dot{x}(t)=r(t)-\frac{1}{T}x(t).
$$

Usando

$$
c(t)=\frac{1}{T}x(t),
$$

obtemos a forma clássica do sistema de primeira ordem em malha fechada:

$$
T\dot{c}(t)+c(t)=r(t),
\qquad
\frac{C(s)}{R(s)}=\frac{1}{Ts+1}.
$$

O próprio notebook ainda avalia a função `rhs` em dois pontos:

- `rhs(0.0, [0.0]) = [1.0]`
- `rhs(0.5, [0.4]) = [0.6]`

Esses valores são compatíveis com $r(t)=1$ e $T=1$, pois

$$
\dot{x}(t)=1-x(t).
$$

---

## Etapa 7 — Geração dos sinais de entrada com `generate_input_signal(...)`

A função `generate_input_signal(data)` converte os atributos dos blocos de entrada em funções temporais.

No diagrama do notebook, o bloco `Block0` gera um degrau unitário. Assim,

$$
r(t)=u(t),
\qquad
R(s)=\frac{1}{s}.
$$

Os valores mostrados no notebook confirmam esse comportamento:

- $r(0.0)=1.0$
- $r(1.0)=1.0$
- $r(2.0)=1.0$

No caso geral, a mesma função também permite montar entradas do tipo rampa, senoide e outras formas configuradas no diagrama.

---

## Etapa 8 — Execução da simulação com `run_simulation(...)`

A função `run_simulation(data, step_size, simulation_time, param_values)` coordena o processo completo de simulação:

1. cria o grafo;
2. categoriza os blocos;
3. gera os sinais de entrada;
4. monta o sistema algébrico;
5. constrói `rhs(t, x)`;
6. integra a dinâmica numericamente.

No notebook, essa chamada devolve:

- `t`: vetor de tempo;
- `input_signal_funcs_sim`: sinais de entrada usados na simulação;
- `input_blocks_sim = ['Block0']`;
- `output_out`, com a saída associada a `Block3`.

Além disso, o notebook mostra:

- `len(t) = 10000`
- os primeiros valores de `c_sim(t)` e da solução analítica coincidem;
- erro máximo aproximado de $1.4044\times 10^{-4}$.

Para entrada degrau unitário e condições iniciais nulas, a solução analítica usada para comparação é

$$
c(t)=1-e^{-t/T}, \qquad t\ge 0.
$$

Assim, a simulação numérica confirma a montagem correta do modelo matemático.

---

## Etapa 9 — Visualização dos resultados com `plot_signals(...)`

A função `plot_signals(t, input_signals, input_blocks, outputs, data_diagram)` gera os gráficos dos sinais de entrada e saída do diagrama.

No notebook, essa visualização é complementada por um segundo gráfico em `matplotlib` que compara:

- a resposta simulada `c_sim(t)`;
- a resposta analítica $1-e^{-t/T}$.

Logo, a etapa de visualização não apenas exibe os sinais, mas também evidencia a concordância entre:

$$
r(t)=u(t)
$$

e

$$
c(t)=1-e^{-t/T}.
$$

---

## Etapa 10 — Incorporação ao notebook com `open_gui(...)`

Por fim, o notebook mostra o uso de

```python
open_gui("diagrams/first_order_step.json")
```

para incorporar a interface gráfica do CSSIM ao ambiente do Jupyter.

Essa etapa não altera o modelo matemático, mas conecta a análise teórica e numérica com a interface visual do diagrama utilizado na simulação.

---

## Forma matemática global do CSSIM

Em resumo, o método do CSSIM pode ser descrito por duas relações acopladas:

$$
\mathbf{y}(t)=\mathbf{M}^{-1}\bigl(\mathbf{H}\,\mathbf{x}(t)+\mathbf{u}_{\text{ext}}(t)\bigr),
$$

$$
\dot{\mathbf{x}}(t)=F\bigl(\mathbf{x}(t),\mathbf{y}(t),\mathbf{u}_{\text{ext}}(t)\bigr).
$$

Eliminando o vetor algébrico $\mathbf{y}(t)$, o problema fica na forma padrão

$$
\dot{\mathbf{x}}(t)=f\bigl(t,\mathbf{x}(t)\bigr).
$$

Essa formulação é útil porque:

- separa a parte algébrica da parte dinâmica;
- trata realimentações de forma sistemática;
- permite combinar vários tipos de bloco em um único modelo;
- produz uma formulação compatível com integração numérica direta.

---

## Consolidação do exemplo de primeira ordem

No exemplo do notebook, a malha fechada pode ser resumida pelas equações

$$
e(t)=r(t)-c(t),
$$

$$
\dot{x}(t)=e(t),
$$

$$
c(t)=\frac{1}{T}x(t).
$$

Substituindo as relações, obtemos

$$
\dot{x}(t)=r(t)-\frac{1}{T}x(t).
$$

Como $c(t)=\frac{1}{T}x(t)$, segue a forma equivalente

$$
T\dot{c}(t)+c(t)=r(t).
$$

No domínio de Laplace,

$$
\frac{C(s)}{R(s)}=\frac{1}{Ts+1}.
$$

Para o degrau unitário,

$$
r(t)=u(t),
$$

e, com condições iniciais nulas,

$$
c(t)=1-e^{-t/T}.
$$

No caso específico do notebook, como $T=1$,

$$
c(t)=1-e^{-t}.
$$

---

## Conclusão

O notebook de primeira ordem mostra, de forma explícita, como o CSSIM passa de um diagrama de blocos para um modelo matemático completo:

1. lê a topologia do sistema em JSON;
2. converte essa topologia em um grafo;
3. resolve parâmetros simbólicos;
4. classifica os blocos por função;
5. converte blocos dinâmicos para espaço de estados;
6. monta o sistema algébrico e a dinâmica global;
7. gera os sinais de entrada;
8. integra numericamente o sistema;
9. visualiza os resultados;
10. incorpora o diagrama ao notebook.

No exemplo estudado, esse processo leva exatamente ao modelo

$$
\dot{x}(t)=r(t)-\frac{1}{T}x(t),
$$

$$
c(t)=\frac{1}{T}x(t),
$$

ou, equivalentemente,

$$
T\dot{c}(t)+c(t)=r(t),
\qquad
\frac{C(s)}{R(s)}=\frac{1}{Ts+1}.
$$

Assim, o documento fica consistente com a estrutura, a nomenclatura e os resultados atualmente apresentados no notebook.
