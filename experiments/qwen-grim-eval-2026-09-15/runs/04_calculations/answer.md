Ниже два разбора. В первом мы увидим, как плоская геометрия выглядит в криволинейных координатах: символы Кристоффеля ненулевые, но тензор Римана равен нулю. Во втором вычислим формы поверхности в точке и проясним смысл симметрии оператора формы.

## 1. Плоскость в полярных координатах

Плоскость геометрически плоская, но полярные координаты «изгибают» координатный базис: векторы \(\partial_r\) и \(\partial_\theta\) меняют направление и длину при движении. Поэтому символы Кристоффеля могут быть ненулевыми, хотя кривизна равна нулю.

Метрика
\[
ds^2=dr^2+r^2d\theta^2
\]
даёт \(g_{rr}=1\), \(g_{\theta\theta}=r^2\), \(g^{rr}=1\), \(g^{\theta\theta}=1/r^2\). Ненулевые символы Кристоффеля для связности Леви-Чивита равны
\[
\Gamma^r_{\theta\theta}=-r,\qquad
\Gamma^\theta_{r\theta}=\Gamma^\theta_{\theta r}=\frac1r.
\]
Например, \(\Gamma^r_{\theta\theta}=-\frac12 g^{rr}\partial_r g_{\theta\theta}\), а \(\Gamma^\theta_{r\theta}=\frac12 g^{\theta\theta}\partial_r g_{\theta\theta}\). Геометрически \(\Gamma^r_{\theta\theta}=-r\) — это центробежная поправка при движении по окружности, а \(\Gamma^\theta_{r\theta}=1/r\) отражает растяжение углового базиса с ростом \(r\).

Постоянный декартов вектор \(V=(1,0)\) запишем в полярном базисе. Так как
\[
\partial_r=(\cos\theta,\sin\theta),\qquad
\partial_\theta=(-r\sin\theta,r\cos\theta),
\]
получаем
\[
V=\cos\theta\,\partial_r-\frac{\sin\theta}{r}\,\partial_\theta.
\]
Обозначим \(V^r=\cos\theta\), \(V^\theta=-\sin\theta/r\). Тогда
\[
\nabla_{\partial_r}V
=
\left(\partial_r V^r+V^\theta\Gamma^r_{\theta r}\right)\partial_r
+
\left(\partial_r V^\theta+V^\theta\Gamma^\theta_{r\theta}\right)\partial_\theta.
\]
Здесь \(\partial_r V^r=0\), \(\Gamma^r_{\theta r}=0\), \(\partial_r V^\theta=\sin\theta/r^2\), а \(V^\theta\Gamma^\theta_{r\theta}=-\sin\theta/r^2\), поэтому \(\nabla_{\partial_r}V=0\).

Далее
\[
\nabla_{\partial_\theta}V
=
\left(\partial_\theta V^r+V^\theta\Gamma^r_{\theta\theta}\right)\partial_r
+
\left(\partial_\theta V^\theta+V^r\Gamma^\theta_{r\theta}\right)\partial_\theta.
\]
Подставляя,
\[
\partial_\theta V^r=-\sin\theta,\quad V^\theta\Gamma^r_{\theta\theta}=\sin\theta,
\]
\[
\partial_\theta V^\theta=-\frac{\cos\theta}{r},\quad V^r\Gamma^\theta_{r\theta}=\frac{\cos\theta}{r},
\]
поэтому \(\nabla_{\partial_\theta}V=0\). Вектор действительно постоянный в евклидовом смысле: ненулевые \(\Gamma\) лишь компенсируют изменение полярного базиса.

Кривизна не читается по отдельным \(\Gamma\), а определяется тензором Римана. Например,
\[
R^r_{\theta r\theta}
=
\partial_r\Gamma^r_{\theta\theta}
-\partial_\theta\Gamma^r_{r\theta}
+\Gamma^r_{r\lambda}\Gamma^\lambda_{\theta\theta}
-\Gamma^r_{\theta\lambda}\Gamma^\lambda_{r\theta}
=
-1-0+0-(-r)\frac1r=0.
\]
В двумерном случае достаточно одной независимой компоненты; она равна нулю, поэтому плоскость плоская.

Перейдём к ортонормированному базису
\[
E_1=\partial_r,\qquad E_2=\frac1r\partial_\theta.
\]
Вычислим
\[
\nabla_{E_1}E_2
=
\nabla_{\partial_r}\left(\frac1r\partial_\theta\right)
=
-\frac1{r^2}\partial_\theta+\frac1r\frac1r\partial_\theta=0,
\]
и
\[
\nabla_{E_2}E_1
=
\frac1r\nabla_{\partial_\theta}\partial_r
=
\frac1r\frac1r\partial_\theta
=
\frac1rE_2.
\]
Следовательно,
\[
\nabla_{E_1}E_2-\nabla_{E_2}E_1=-\frac1rE_2.
\]
Коммутатор
\[
[E_1,E_2]=\left[\partial_r,\frac1r\partial_\theta\right]
=
-\frac1{r^2}\partial_\theta=-\frac1rE_2.
\]
Кручение определяется как
\[
T(X,Y)=\nabla_XY-\nabla_YX-[X,Y],
\]
поэтому
\[
T(E_1,E_2)=0.
\]
Разность производных не равна нулю, потому что \(E_1,E_2\) — не координатный базис; для связности Леви-Чивита она равна коммутатору, и кручение исчезает.

## 2. Поверхность в параметрах \((u,v)\)

Поверхность
\[
\mathbf r(u,v)=\left(u+v,\ v,\ \frac{(u+v)^2+2v^2}{2}\right)
\]
вблизи точки \((0,0)\) есть график \(z=\frac12x^2+y^2\), где \(x=u+v\), \(y=v\). Это подсказывает, что главные направления будут вдоль координатных осей \(x\) и \(y\).

В точке \((0,0)\):
\[
\mathbf r_u=(1,0,0),\qquad \mathbf r_v=(1,1,0).
\]
Поверхность регулярна, так что \(\mathbf r_u\times\mathbf r_v\ne0\). Первая фундаментальная форма:
\[
I=\begin{pmatrix}
\mathbf r_u\cdot \mathbf r_u & \mathbf r_u\cdot \mathbf r_v\\
\mathbf r_v\cdot \mathbf r_u & \mathbf r_v\cdot \mathbf r_v
\end{pmatrix}
=
\begin{pmatrix}
1 & 1\\
1 & 2
\end{pmatrix}.
\]
Нормаль с положительной третьей компонентой:
\[
n=\frac{\mathbf r_u\times \mathbf r_v}{\|\mathbf r_u\times \mathbf r_v\|}=(0,0,1).
\]
Вторые производные:
\[
\mathbf r_{uu}=(0,0,1),\quad \mathbf r_{uv}=(0,0,1),\quad \mathbf r_{vv}=(0,0,3).
\]
Поэтому вторая фундаментальная форма
\[
II=\begin{pmatrix}
\mathbf r_{uu}\cdot n & \mathbf r_{uv}\cdot n\\
\mathbf r_{uv}\cdot n & \mathbf r_{vv}\cdot n
\end{pmatrix}
=
\begin{pmatrix}
1 & 1\\
1 & 3
\end{pmatrix}.
\]
Матрицы \(I\) и \(II\) симметричны, потому что соответствующие билинейные формы симметричны; матрица оператора формы в том же базисе может выглядеть несимметричной.

Оператор формы \(S=-dn\) связан с формами соотношением
\[
II(X,Y)=\langle S X,Y\rangle,
\]
поэтому в координатном базисе \((\mathbf r_u,\mathbf r_v)\) его матрица равна
\[
S=I^{-1}II.
\]
Здесь
\[
I^{-1}=\begin{pmatrix}2&-1\\-1&1\end{pmatrix},
\]
откуда
\[
S=\begin{pmatrix}2&-1\\-1&1\end{pmatrix}
\begin{pmatrix}1&1\\1&3\end{pmatrix}
=
\begin{pmatrix}1&-1\\0&2\end{pmatrix}.
\]
Матрица \(S\) не симметрична в обычном смысле, но она самосопряжённая относительно первой формы:
\[
S^T I=IS=II.
\]
Именно это означает симметричность оператора формы: \(\langle SX,Y\rangle=\langle X,SY\rangle\). В ортонормированном базисе касательного пространства такая матрица была бы симметричной.

Собственные значения \(S\): \(1\) и \(2\). Собственный вектор при \(\lambda=1\) имеет координаты \((1,0)\), а при \(\lambda=2\) — \((1,-1)\). В декартовом виде это направления
\[
\mathbf r_u=(1,0,0),\qquad \mathbf r_u-\mathbf r_v=(0,-1,0),
\]
то есть оси \(x\) и \(y\). Оба направления единичны: \(I((1,0),(1,0))=1\), \(I((1,-1),(1,-1))=1\).

Для направления с координатными компонентами \(v=(1,0)\) нормальная кривизна равна
\[
\kappa_n=\frac{II(v,v)}{I(v,v)}
=
\frac{1}{1}=1.
\]
Это совпадает с соответствующей главной кривизной, поскольку \(v\) — собственное направление оператора формы.