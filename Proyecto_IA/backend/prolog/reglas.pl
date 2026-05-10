% =========================================
% Reglas de recomendación visual
% =========================================

% recomendacion(TipoGrafico, Columnas, Justificacion)

% -------------------------
% Univariados Generales
% -------------------------
recomendacion(histograma, Col, 'Variable continua detectada para ver su distribución.') :-
    \+ audiencia(ejecutiva),
    tipo_columna(Col, continua).

recomendacion(barras, Col, 'Variable discreta detectada.') :-
    tipo_columna(Col, discreta).

recomendacion(barras, Col, 'Variable categórica detectada (pocas categorías).') :-
    tipo_columna(Col, categorica),
    (num_categorias(Col, N), N =< 15 ; \+ num_categorias(Col, _)).

recomendacion(barras, Col, 'Variable binaria detectada.') :-
    tipo_columna(Col, binaria).

recomendacion(barras, Col, 'Variable booleana detectada.') :-
    tipo_columna(Col, booleana).

% -------------------------
% Audiencia Ejecutiva
% -------------------------
recomendacion(kpi, Col, 'Indicador clave (KPI) preferido por la audiencia ejecutiva.') :-
    audiencia(ejecutiva),
    (tipo_columna(Col, continua) ; tipo_columna(Col, discreta)).

recomendacion(pastel, Col, 'Proporciones simples para audiencia ejecutiva.') :-
    audiencia(ejecutiva),
    tipo_columna(Col, categorica),
    num_categorias(Col, N), N =< 5.

% -------------------------
% Temporales + numéricas
% -------------------------
recomendacion(lineas, par(Fecha, Valor), 'Evolución en el tiempo (serie temporal continua).') :-
    tipo_columna(Fecha, temporal),
    tipo_columna(Valor, continua),
    Fecha \= Valor.

recomendacion(lineas, par(Fecha, Valor), 'Evolución en el tiempo (serie temporal discreta).') :-
    tipo_columna(Fecha, temporal),
    tipo_columna(Valor, discreta),
    Fecha \= Valor.

% -------------------------
% Relación entre numéricas
% -------------------------
recomendacion(dispersion, par(X, Y), 'Correlación entre dos variables numéricas.') :-
    \+ audiencia(no_tecnica),
    \+ audiencia(ejecutiva),
    tipo_columna(X, continua),
    tipo_columna(Y, continua),
    X @< Y.

recomendacion(dispersion, par(X, Y), 'Variable continua contra discreta para explorar relación.') :-
    \+ audiencia(no_tecnica),
    \+ audiencia(ejecutiva),
    tipo_columna(X, continua),
    tipo_columna(Y, discreta),
    X \= Y.

recomendacion(dispersion, par(X, Y), 'Variable discreta contra continua para explorar relación.') :-
    \+ audiencia(no_tecnica),
    \+ audiencia(ejecutiva),
    tipo_columna(X, discreta),
    tipo_columna(Y, continua),
    X \= Y.

% -------------------------
% Audiencia técnica (Avanzados)
% -------------------------
recomendacion(boxplot, Col, 'Distribución y detección de outliers (audiencia técnica).') :-
    audiencia(tecnica),
    tipo_columna(Col, continua).

recomendacion(mapa_calor, par(X, Y), 'Relación entre dos variables categóricas (audiencia técnica).') :-
    audiencia(tecnica),
    tipo_columna(X, categorica),
    tipo_columna(Y, categorica),
    num_categorias(X, NX), NX =< 10,
    num_categorias(Y, NY), NY =< 10,
    X @< Y.

% -------------------------
% Evitar gráficos directos
% -------------------------
recomendacion(no_graficar_directamente, Col, 'Texto libre no es recomendable para un gráfico directo.') :-
    tipo_columna(Col, texto_libre).

recomendacion(no_graficar_directamente, Col, 'El identificador no aporta valor en un gráfico.') :-
    tipo_columna(Col, identificador).

recomendacion(tabla, Col, 'Variable categórica con muchas categorías es mejor en tabla.') :-
    tipo_columna(Col, categorica),
    num_categorias(Col, N), N > 15.