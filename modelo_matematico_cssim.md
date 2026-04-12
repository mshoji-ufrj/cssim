# Montagem do modelo matemático no CSSIM com foco em espaço de estados

Este documento reescreve, de forma mais didática, o fluxo apresentado no notebook [cssim_first_order.ipynb](cssim_first_order.ipynb). O objetivo é mostrar como o CSSIM transforma um diagrama de blocos em um modelo dinâmico em espaço de estados, pronto para simulação numérica.

O exemplo usado ao longo do texto é o sistema de primeira ordem definido em [diagrams/first_order_step.json](diagrams/first_order_step.json).

---

## 1. Ideia central: por que usar espaço de estados?

Em teoria de controle, um sistema dinâmico pode ser descrito de duas formas muito comuns:

- por **função de transferência**, no domínio de Laplace;
- por **equações de estado**, no domínio do tempo.

Na forma de espaço de estados, descrevemos o sistema por meio de variáveis internas chamadas **estados**. Essas variáveis guardam a “memória” do sistema.

A forma padrão é

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}\,\mathbf{u}(t),
$$

$$
\mathbf{y}(t)=\mathbf{C}\,\mathbf{x}(t)+\mathbf{D}\,\mathbf{u}(t),
$$

em que:

- $\mathbf{x}(t)$ é o vetor de estados;
- $\mathbf{u}(t)$ é o vetor de entradas;
- $\mathbf{y}(t)$ é o vetor de saídas;
- $\mathbf{A},\mathbf{B},\mathbf{C},\mathbf{D}$ são matrizes do modelo.

Ao longo deste texto, para manter a simbologia tradicional de espaço de estados, a letra $\mathbf{y}(t)$ será reservada para a **saída do sistema**. Quando for necessário representar sinais internos algébricos da interconexão, usaremos outra notação.

Da mesma forma, a letra $G$ será reservada para **função de transferência**, como em $G(s)$. Por isso, as matrizes auxiliares da montagem algébrica usarão outras letras.

Essa forma é especialmente útil no CSSIM porque o simulador precisa trabalhar no tempo, calculando a derivada dos estados a cada instante. Em outras palavras, o integrador numérico não simula diretamente uma função de transferência; ele simula uma EDO do tipo

$$
\dot{\mathbf{x}}(t)=f\bigl(t,\mathbf{x}(t)\bigr).
$$

Portanto, a tarefa principal do CSSIM é converter o diagrama de blocos em uma descrição equivalente nessa forma.

---

## 2. O que o CSSIM faz, em termos conceituais

Ao ler um diagrama, o CSSIM separa os blocos em dois grupos principais:

1. **blocos dinâmicos**, que introduzem estados;
2. **blocos algébricos**, que apenas combinam sinais instantaneamente.

Isso leva naturalmente a duas camadas matemáticas:

- uma camada **algébrica**, que resolve sinais internos como somas, ganhos e realimentações;
- uma camada **dinâmica**, que calcula $\dot{\mathbf{x}}(t)$ a partir desses sinais.

De forma resumida, o CSSIM:

1. lê o JSON do diagrama;
2. constrói o grafo de interconexões;
3. resolve parâmetros simbólicos;
4. identifica quais blocos têm estado;
5. converte blocos dinâmicos para matrizes de espaço de estados;
6. monta o acoplamento algébrico entre os sinais;
7. produz a função $f(t,\mathbf{x})$ usada pelo integrador;
8. executa a simulação e reconstrói as saídas.

As principais funções envolvidas nesse processo são:

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

## 3. Contexto do exemplo de primeira ordem

Antes de iniciar o fluxo, o notebook fixa o contexto do problema:

- define o símbolo de Laplace $s$;
- define `diagram_path = "diagrams/first_order_step.json"`;
- assume $T=1$;
- monta `param_values = {"T": 1}`;
- registra os parâmetros com `set_parameters(param_values)`;
- carrega o diagrama com `data = load_json(diagram_path)`.

Do ponto de vista de controle clássico, a malha fechada estudada é

$$
E(s)=R(s)-C(s),
\qquad
G(s)=\frac{1}{Ts},
\qquad
C(s)=G(s)E(s).
$$

Ao fechar a malha, obtém-se

$$
\frac{C(s)}{R(s)}=\frac{1}{Ts+1}.
$$

O papel do CSSIM é chegar a esse mesmo comportamento, mas pelo caminho do espaço de estados.

---

## 4. As 10 etapas do fluxo no CSSIM

### Etapa 1 — Leitura do diagrama com `load_json(...)`

A função `load_json(path)` lê o arquivo JSON e devolve a estrutura do diagrama, contendo ao menos:

- `blocks`;
- `connections`;
- `sim_time`;
- `step_size`.

No exemplo, o arquivo descreve:

- um bloco de entrada do tipo degrau;
- um somador com sinais `+` e `-`;
- um bloco dinâmico com função de transferência $\frac{1}{Ts}$;
- um bloco de saída.

Nesta etapa, ainda não existe equação de estado. O que existe é apenas a **topologia** do sistema.

---

### Etapa 2 — Construção do grafo com `build_graph(...)`

A função `build_graph(data)` transforma o diagrama em um grafo direcionado. Isso é importante porque o simulador precisa saber:

- de onde vem cada sinal;
- para onde cada sinal vai;
- quais blocos alimentam outros blocos;
- onde existe realimentação.

No exemplo, o grafo identifica essencialmente o seguinte fluxo:

$$
	\text{entrada} \to \text{somador} \to \text{bloco dinâmico} \to \text{saída},
$$

com a realimentação da saída voltando ao somador.

Em termos conceituais, essa etapa organiza o diagrama para que o CSSIM consiga escrever as equações corretamente.

---

### Etapa 3 — Resolução dos parâmetros com `set_parameters(...)` e `resolve_param(...)`

Nos diagramas do CSSIM, parâmetros podem aparecer como expressões simbólicas, por exemplo:

- `T`
- `K`
- `2*zeta*wn`
- `wn**2`

No caso do notebook, o parâmetro relevante é $T$, com valor

$$
T=1.
$$

Ao resolver os parâmetros, o bloco dinâmico deixa de ser interpretado como algo simbólico e passa a ter coeficientes numéricos. Isso é indispensável porque a simulação exige matrizes numéricas.

No exemplo,

$$
\frac{1}{Ts}\quad \longrightarrow \quad \frac{1}{1\cdot s}=\frac{1}{s}.
$$

---

### Etapa 4 — Categorização dos blocos com `categorize_blocks(...)`

Nem todo bloco gera estado. Por isso, o CSSIM classifica os blocos por função.

No notebook, a categorização produz:

- `input_blocks = ['Block0']`
- `tf_blocks = ['Block2']`
- `static_blocks = ['Block1']`
- `pid_blocks = []`
- `output_blocks = ['Block3']`
- `total_states = 1`

Essa informação é crucial para a teoria de espaço de estados:

- blocos de entrada definem $\mathbf{u}(t)$;
- blocos dinâmicos contribuem para $\mathbf{x}(t)$;
- blocos algébricos ajudam a montar relações instantâneas entre sinais;
- blocos de saída definem quais sinais devem ser observados ao final.

No exemplo existe apenas **um estado**, então o vetor global é simplesmente

$$
\mathbf{x}(t)=x(t).
$$

---

### Etapa 5 — Da função de transferência para espaço de estados com `tf_to_ss(...)`

Aqui aparece a ponte entre controle clássico e controle moderno.

O bloco dinâmico do exemplo é

$$
G(s)=\frac{1}{Ts}.
$$

A função `tf_to_ss(num, den, param_values=None)` converte essa função de transferência em uma realização no formato

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}\,u(t),
$$

$$
y(t)=\mathbf{C}\,\mathbf{x}(t)+\mathbf{D}\,u(t).
$$

No notebook, a chamada é:

```python
A_tf, B_tf, C_tf, D_tf = tf_to_ss("1", "T*s", param_values={"T": 1})
```

Com $T=1$, o resultado mostrado é

$$
\mathbf{A}=[0],
\qquad
\mathbf{B}=[1],
\qquad
\mathbf{C}=[1],
\qquad
\mathbf{D}=0.
$$

Isso significa que, para esse bloco,

$$
\dot{x}(t)=u(t),
\qquad
y(t)=x(t).
$$

Se mantivermos $T$ explícito, a interpretação é

$$
\dot{x}(t)=e(t),
\qquad
c(t)=\frac{1}{T}x(t).
$$

Ou seja:

- o estado é a integral do sinal de entrada do bloco;
- a saída do bloco é obtida a partir do estado.

Esse é o ponto mais importante da teoria de espaço de estados no exemplo: o integrador $\frac{1}{Ts}$ deixa de ser apenas um bloco em Laplace e passa a ser representado por uma variável de estado com dinâmica própria.

---

### Etapa 6 — Montagem do modelo completo com `build_solver(...)` e `compute_rhs(...)`

Esta é a etapa central.

Depois que cada bloco dinâmico já foi convertido para espaço de estados, ainda falta combinar todos os blocos do diagrama em um único modelo global. O CSSIM faz isso em duas partes.

#### Parte algébrica: resolver os sinais internos

Blocos como somadores, ganhos e conexões não criam novos estados. Eles apenas impõem relações instantâneas entre sinais.

O CSSIM reúne essas relações em um sistema do tipo

$$
\mathbf{M}\,\mathbf{w}(t)=\mathbf{H}\,\mathbf{x}(t)+\mathbf{P}\,\mathbf{u}(t),
$$

em que:

- $\mathbf{x}(t)$ é o vetor de estados globais;
- $\mathbf{u}(t)$ é o vetor de entradas externas;
- $\mathbf{w}(t)$ reúne sinais internos do diagrama;
- $\mathbf{M}$ descreve o acoplamento algébrico entre esses sinais;
- $\mathbf{H}$ mostra como os estados influenciam as equações algébricas;
- $\mathbf{P}$ mostra como as entradas externas aparecem nessas equações algébricas.

Se $\mathbf{M}$ é inversível, então

$$
\mathbf{w}(t)=\mathbf{M}^{-1}\bigl(\mathbf{H}\,\mathbf{x}(t)+\mathbf{P}\,\mathbf{u}(t)\bigr).
$$

Em linguagem simples: dado o estado atual e a entrada atual, o CSSIM calcula instantaneamente todos os sinais internos relevantes.

#### Parte dinâmica: calcular a derivada dos estados

Depois de conhecer os sinais internos, o CSSIM calcula a dinâmica global na forma

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}_w\,\mathbf{w}(t)+\mathbf{B}_u\,\mathbf{u}(t).
$$

Essa equação vem diretamente da teoria de espaço de estados aplicada ao conjunto de blocos dinâmicos do diagrama.

Para entender sua origem, vale começar pelo caso de **um único bloco dinâmico**. Sim: essas são justamente as equações usuais de espaço de estados para um bloco. Para manter a notação tradicional, podemos escrevê-las como

$$
\dot{\mathbf{x}}_i(t)=\mathbf{A}_i\,\mathbf{x}_i(t)+\mathbf{B}_i\,\mathbf{u}_i(t),
$$

$$
\mathbf{y}_i(t)=\mathbf{C}_i\,\mathbf{x}_i(t)+\mathbf{D}_i\,\mathbf{u}_i(t),
$$

em que:

- $\mathbf{x}_i(t)$ é o vetor de estados internos do bloco $i$;
- $\mathbf{u}_i(t)$ é a entrada desse bloco;
- $\mathbf{y}_i(t)$ é a saída desse bloco;
- $\mathbf{A}_i,\mathbf{B}_i,\mathbf{C}_i,\mathbf{D}_i$ são as matrizes da realização em espaço de estados daquele bloco.

Essas são as formas tradicionais da teoria de espaço de estados: a primeira equação descreve a dinâmica interna do bloco, e a segunda descreve como a saída do bloco é obtida a partir dos estados e da entrada.

Quando o diagrama possui vários blocos dinâmicos, o CSSIM empilha todos esses estados em um único vetor global:

$$
\mathbf{x}(t)=\begin{pmatrix}
\mathbf{x}_1(t) \\
\mathbf{x}_2(t) \\
\vdots \\
\mathbf{x}_n(t)
\end{pmatrix}.
$$

Ao fazer isso, todas as equações diferenciais locais são reunidas em uma única equação global. É daí que surge a expressão

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}_w\,\mathbf{w}(t)+\mathbf{B}_u\,\mathbf{u}(t).
$$

Ela diz que a derivada do vetor de estados globais pode depender de três tipos de contribuição:

1. do próprio estado atual $\mathbf{x}(t)$;
2. dos sinais internos do diagrama, reunidos em $\mathbf{w}(t)$;
3. das entradas externas do sistema, reunidas em $\mathbf{u}(t)$.

Os elementos da equação são:

- $\dot{\mathbf{x}}(t)$: vetor derivada dos estados, isto é, a taxa de variação de cada estado do sistema;
- $\mathbf{x}(t)$: vetor global de estados, formado pela concatenação dos estados de todos os blocos dinâmicos;
- $\mathbf{w}(t)$: vetor de sinais internos já resolvidos pela parte algébrica, como saídas de somadores, saídas intermediárias e sinais de realimentação;
- $\mathbf{u}(t)$: vetor de entradas externas, como degrau, rampa, senoide ou qualquer sinal aplicado a partir dos blocos de entrada;
- $\mathbf{A}$: matriz que descreve como os próprios estados influenciam suas derivadas;
- $\mathbf{B}_w$: matriz que descreve como os sinais internos do diagrama influenciam a dinâmica dos estados;
- $\mathbf{B}_u$: matriz que descreve como as entradas externas atuam diretamente sobre a dinâmica global.

Em termos físicos, pode-se ler a equação assim:

> a evolução do sistema em cada instante depende da memória acumulada nos estados, dos sinais que circulam internamente na malha e dos sinais externos aplicados ao sistema.

No CSSIM, a presença de $\mathbf{w}(t)$ é importante porque a entrada de um bloco dinâmico nem sempre vem diretamente de uma entrada externa. Muitas vezes ela vem da saída de um somador, de um ganho ou de uma realimentação. Por isso, antes de calcular $\dot{\mathbf{x}}(t)$, o simulador precisa primeiro resolver essas relações algébricas internas.

Em alguns textos de teoria de controle, aparece apenas a forma mais tradicional

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}\,\mathbf{u}(t).
$$

Aqui o CSSIM usa uma forma um pouco mais geral porque separa explicitamente:

- a influência das entradas externas $\mathbf{u}(t)$;
- a influência dos sinais internos $\mathbf{w}(t)$, que surgem da interconexão entre blocos.

Depois que $\mathbf{w}(t)$ é substituído pela solução algébrica da malha, a equação volta para uma forma explícita apenas em função de $\mathbf{x}(t)$ e $\mathbf{u}(t)$.

Substituindo a expressão de $\mathbf{w}(t)$, o resultado fica totalmente em função de $\mathbf{x}(t)$ e $\mathbf{u}(t)$:

$$
\dot{\mathbf{x}}(t)=\bigl(\mathbf{A}+\mathbf{B}_w\,\mathbf{M}^{-1}\mathbf{H}\bigr)\mathbf{x}(t)+\bigl(\mathbf{B}_w\,\mathbf{M}^{-1}\mathbf{P}+\mathbf{B}_u\bigr)\mathbf{u}(t).
$$

Para manter a simbologia mais usual de espaço de estados, podemos simplesmente redefinir as matrizes equivalentes do sistema completo como

$$
\mathbf{A}\coloneqq \mathbf{A}+\mathbf{B}_w\,\mathbf{M}^{-1}\mathbf{H},
\qquad
\mathbf{B}\coloneqq \mathbf{B}_w\,\mathbf{M}^{-1}\mathbf{P}+\mathbf{B}_u,
$$

isto é, daqui em diante $\mathbf{A}$ e $\mathbf{B}$ passam a representar as matrizes efetivas do sistema já com a interconexão algébrica incorporada. Com essa convenção, o modelo volta à forma clássica

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}\,\mathbf{u}(t).
$$

Se desejado, a saída externa do sistema pode então ser escrita na forma usual

$$
\mathbf{y}(t)=\mathbf{C}\,\mathbf{x}(t)+\mathbf{D}\,\mathbf{u}(t).
$$

É essa função que `compute_rhs(...)` entrega ao integrador numérico.

---

#### Aplicação da etapa 6 ao exemplo de primeira ordem

Nesta etapa, vale retomar a formulação teórica apresentada antes e identificar, termo a termo, o que ela se torna no exemplo.

De forma geral, o CSSIM separa o problema em duas partes:

$$
\mathbf{M}\,\mathbf{w}(t)=\mathbf{H}\,\mathbf{x}(t)+\mathbf{P}\,\mathbf{u}(t)
$$

e

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}_w\,\mathbf{w}(t)+\mathbf{B}_u\,\mathbf{u}(t).
$$

No sistema de primeira ordem do notebook, essas grandezas assumem uma forma muito simples.

Primeiro, o vetor de estados tem dimensão 1, pois existe apenas um bloco dinâmico com um único estado interno:

$$
\mathbf{x}(t)=x(t).
$$

A entrada externa é apenas a referência do sistema, portanto

$$
\mathbf{u}(t)=r(t).
$$

Já os sinais internos relevantes da interconexão são escolhidos como

$$
\mathbf{w}(t)=\begin{pmatrix} e(t) \\ c(t) \end{pmatrix},
$$

em que:

- $e(t)$ é o erro na saída do somador;
- $c(t)$ é a saída do bloco dinâmico, isto é, a saída interna da planta.

Com essa escolha, a equação algébrica geral

$$
\mathbf{M}\,\mathbf{w}(t)=\mathbf{H}\,\mathbf{x}(t)+\mathbf{P}\,\mathbf{u}(t)
$$

passa a representar exatamente as duas relações literais do diagrama:

$$
e(t)=r(t)-c(t)
$$

e

$$
c(t)=\frac{1}{T}x(t).
$$

Se escrevermos a primeira equação na forma $e(t)+c(t)=r(t)$, o sistema pode ser colocado matricialmente. Para evitar problemas de renderização, é mais seguro definir cada objeto separadamente:

$$
\mathbf{w}(t)=\begin{bmatrix} e(t) \\ c(t) \end{bmatrix}
$$

$$
\mathbf{M}=\begin{bmatrix} 1 & 1 \\ 0 & 1 \end{bmatrix}
$$

$$
\mathbf{H}=\begin{bmatrix} 0 \\ \frac{1}{T} \end{bmatrix}
$$

$$
\mathbf{P}=\begin{bmatrix} 1 \\ 0 \end{bmatrix}
$$

Assim, a equação algébrica do exemplo fica simplesmente

$$
\mathbf{M}\,\mathbf{w}(t)=\mathbf{H}\,x(t)+\mathbf{P}\,r(t).
$$

Escrevendo essa igualdade por componentes, obtemos exatamente

$$
e(t)+c(t)=r(t)
$$

e

$$
c(t)=\frac{1}{T}x(t).
$$

Isso mostra com clareza o papel de cada termo:

- $\mathbf{M}$ codifica o acoplamento entre os sinais internos $e(t)$ e $c(t)$;
- $\mathbf{H}x(t)$ representa a contribuição do estado sobre a saída do bloco dinâmico;
- $\mathbf{P}r(t)$ injeta a referência na equação do somador.

Como $\mathbf{M}$ é inversível, podemos resolver explicitamente os sinais internos:

$$
\mathbf{w}(t)=\mathbf{M}^{-1}\bigl(\mathbf{H}x(t)+\mathbf{P}r(t)\bigr).
$$

No caso em questão,

$$
\mathbf{M}^{-1}=\begin{pmatrix}1 & -1 \\ 0 & 1\end{pmatrix},
$$

e a resolução devolve exatamente

$$
e(t)=r(t)-\frac{1}{T}x(t),
\qquad
c(t)=\frac{1}{T}x(t).
$$

Agora passamos para a equação dinâmica geral:

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}_w\,\mathbf{w}(t)+\mathbf{B}_u\,\mathbf{u}(t).
$$

No exemplo, a realização em espaço de estados do bloco $\frac{1}{Ts}$ fornece a equação literal

$$
\dot{x}(t)=e(t).
$$

Isto significa que:

- não há contribuição direta do próprio estado na dinâmica do integrador;
- a derivada depende diretamente do primeiro componente de $\mathbf{w}(t)$, que é o erro $e(t)$;
- não há ação direta da entrada externa sobre a dinâmica, sem passar antes pelo somador.

Em notação matricial, isso equivale a escrever

$$
\dot{x}(t)=0\cdot x(t)+\begin{pmatrix}1 & 0\end{pmatrix}
\begin{pmatrix}e(t) \\ c(t)\end{pmatrix}+0\cdot r(t).
$$

Portanto, neste exemplo,

$$
\mathbf{A}=[0],
\qquad
\mathbf{B}_w=\begin{pmatrix}1 & 0\end{pmatrix},
\qquad
\mathbf{B}_u=[0].
$$

Substituindo a expressão de $\mathbf{w}(t)$, obtemos a dinâmica fechada:

$$
\dot{x}(t)=e(t)=r(t)-\frac{1}{T}x(t).
$$

Esta é a EDO que o CSSIM efetivamente integra.

Essa passagem deixa claro o encadeamento lógico da montagem do modelo:

1. o sistema algébrico calcula o erro $e(t)$ e a saída interna $c(t)$;
2. a equação dinâmica usa esse erro como entrada do integrador;
3. a substituição elimina as variáveis intermediárias e produz uma única EDO explícita.

Observe o significado físico dessa equação:

- se o estado ainda é pequeno, a saída também é pequena, então o erro é grande;
- erro grande implica derivada grande, isto é, o estado cresce rapidamente;
- à medida que a saída se aproxima da referência, o erro diminui;
- por isso a resposta converge de forma exponencial.

Se quisermos escrever o resultado em termos da saída do sistema, usamos

$$
c(t)=\frac{1}{T}x(t).
$$

Derivando ambos os lados,

$$
\dot{c}(t)=\frac{1}{T}\dot{x}(t).
$$

Substituindo a dinâmica de $x(t)$,

$$
\dot{c}(t)=\frac{1}{T}r(t)-\frac{1}{T}c(t),
$$

ou, equivalentemente,

$$
T\dot{c}(t)+c(t)=r(t).
$$

Portanto, a formulação em espaço de estados reproduz exatamente, para este exemplo, o modelo literal conhecido da malha fechada de primeira ordem.

---

#### O que `build_solver(...)` fornece no exemplo

No notebook, a chamada a `build_solver(...)` produz objetos como:

- `w_ids = ['Block1', 'Block2']`
- `w_index = {'Block1': 0, 'Block2': 1}`
- `M_inv = [[1, -1], [0, 1]]`
- `P_u_terms = {0: [('Block0', 1.0)], 1: []}`
- `H = [[0], [1]]`

Didaticamente, isso significa:

- `w_ids` indica quais sinais compõem o vetor algébrico $\mathbf{w}(t)$;
- existe uma relação linear entre esses sinais;
- essa relação pode ser resolvida imediatamente por meio de $\mathbf{M}^{-1}$;
- a contribuição dos estados aparece em `H`;
- as contribuições das entradas externas aparecem em `P_u_terms`.

No fundo, `build_solver(...)` organiza a pergunta:

> dado o estado atual e a entrada atual, quanto vale cada sinal interno da malha?

Já `compute_rhs(...)` responde à pergunta seguinte:

> sabendo os sinais internos, quanto vale a derivada do estado agora?

Essa separação é bastante natural em espaço de estados: primeiro resolvemos as relações instantâneas; depois propagamos a dinâmica no tempo.

---

### Etapa 7 — Geração dos sinais de entrada com `generate_input_signal(...)`

Os blocos de entrada do diagrama são convertidos em funções do tempo.

No exemplo, a referência é um degrau unitário:

$$
r(t)=u(t),
\qquad
R(s)=\frac{1}{s}.
$$

Isso significa que o sistema em espaço de estados será excitado por uma entrada constante igual a 1 para $t\ge 0$.

---

### Etapa 8 — Simulação numérica com `run_simulation(...)`

A função `run_simulation(data, step_size, simulation_time, param_values)` coordena todo o processo:

1. monta o grafo;
2. classifica os blocos;
3. gera as entradas;
4. constrói o sistema algébrico;
5. gera a função `rhs(t, x)`;
6. integra a EDO.

No exemplo, a EDO integrada é

$$
\dot{x}(t)=1-x(t),
$$

pois $T=1$ e a entrada é um degrau unitário.

Com condição inicial nula, a solução analítica é

$$
x(t)=1-e^{-t}.
$$

Como neste caso $c(t)=x(t)$, a saída também é

$$
c(t)=1-e^{-t}.
$$

O notebook mostra que a solução numérica coincide com a solução analítica com erro muito pequeno, confirmando que a montagem do modelo está correta.

---

### Etapa 9 — Visualização com `plot_signals(...)`

Após integrar o sistema, o CSSIM reconstrói e plota os sinais de interesse.

Do ponto de vista didático, essa etapa é importante porque conecta três níveis de descrição do mesmo sistema:

1. **diagrama de blocos**;
2. **equação de estado**;
3. **resposta temporal**.

Quando o gráfico da simulação coincide com a curva analítica $1-e^{-t/T}$, isso mostra que a passagem do diagrama para o modelo em espaço de estados foi feita corretamente.

---

### Etapa 10 — Integração com o notebook via `open_gui(...)`

A chamada

```python
open_gui("diagrams/first_order_step.json")
```

incorpora a interface visual do CSSIM ao notebook. Essa etapa não altera a matemática do problema, mas facilita a ligação entre:

- a representação gráfica do sistema;
- sua formulação matemática;
- os resultados da simulação.

---

## 5. Resumo matemático global do CSSIM

Em uma forma mais geral, o CSSIM trabalha com duas camadas acopladas.

Primeiro, a camada algébrica:

$$
\mathbf{w}(t)=\mathbf{M}^{-1}\bigl(\mathbf{H}\,\mathbf{x}(t)+\mathbf{P}\,\mathbf{u}(t)\bigr).
$$

Depois, a camada dinâmica:

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}_w\,\mathbf{w}(t)+\mathbf{B}_u\,\mathbf{u}(t).
$$

Substituindo a primeira na segunda, e usando $\mathbf{A}$ e $\mathbf{B}$ para denotar as matrizes equivalentes do sistema completo, obtemos a forma padrão de simulação:

$$
\dot{\mathbf{x}}(t)=\mathbf{A}\,\mathbf{x}(t)+\mathbf{B}\,\mathbf{u}(t).
$$

e a saída externa pode ser escrita, na notação tradicional, como

$$
\mathbf{y}(t)=\mathbf{C}\,\mathbf{x}(t)+\mathbf{D}\,\mathbf{u}(t).
$$

Esse procedimento é exatamente o que se espera de uma abordagem em espaço de estados aplicada a diagramas de blocos: identificar os estados, resolver as interconexões e produzir uma EDO explícita.

---

## 6. Consolidação do exemplo de primeira ordem

No exemplo do notebook, a malha pode ser resumida pelas equações

$$
e(t)=r(t)-c(t),
$$

$$
\dot{x}(t)=e(t),
$$

$$
c(t)=\frac{1}{T}x(t).
$$

Eliminando as variáveis intermediárias, obtemos

$$
\dot{x}(t)=r(t)-\frac{1}{T}x(t).
$$

Em termos da saída,

$$
T\dot{c}(t)+c(t)=r(t).
$$

No domínio de Laplace,

$$
\frac{C(s)}{R(s)}=\frac{1}{Ts+1}.
$$

Para um degrau unitário e condições iniciais nulas,

$$
c(t)=1-e^{-t/T}.
$$

Quando $T=1$,

$$
c(t)=1-e^{-t}.
$$

---

## 7. Conclusão

O ponto principal do notebook não é apenas simular um sistema de primeira ordem, mas mostrar como um diagrama de blocos pode ser reinterpretado em linguagem de espaço de estados.

No CSSIM, esse processo ocorre assim:

1. o diagrama fornece a estrutura de interconexão;
2. os blocos dinâmicos são convertidos para matrizes de estado;
3. os blocos algébricos geram relações lineares entre sinais internos;
4. essas relações são combinadas em uma EDO explícita;
5. o integrador numérico resolve essa EDO no tempo.

No exemplo estudado, tudo se reduz ao modelo

$$
\dot{x}(t)=r(t)-\frac{1}{T}x(t),
\qquad
c(t)=\frac{1}{T}x(t),
$$

que é equivalente a

$$
T\dot{c}(t)+c(t)=r(t),
\qquad
\frac{C(s)}{R(s)}=\frac{1}{Ts+1}.
$$

Assim, o CSSIM conecta de forma natural três perspectivas do mesmo sistema:

- a estrutura do diagrama de blocos;
- a teoria de espaço de estados;
- a resposta temporal obtida por simulação.
