"""Independent symbolic calculations for the diagnostic tasks (requires sympy)."""
import json
from pathlib import Path
import sympy as s

r, theta = s.symbols('r theta', positive=True)
coords = [r, theta]
g = s.diag(1, r**2)
gi = g.inv()
Gamma = [[[s.simplify(sum(gi[k,l] * (s.diff(g[l,j], coords[i]) + s.diff(g[l,i], coords[j]) - s.diff(g[i,j], coords[l])) / 2 for l in range(2))) for j in range(2)] for i in range(2)] for k in range(2)]


def nabla(X, Y):
    return s.simplify(s.Matrix([sum(X[i] * (s.diff(Y[k], coords[i]) + sum(Gamma[k][i][j] * Y[j] for j in range(2))) for i in range(2)) for k in range(2)]))


V = s.Matrix([s.cos(theta), -s.sin(theta)/r])
e1, e2 = s.Matrix([1, 0]), s.Matrix([0, 1/r])
bracket = s.simplify(e2.jacobian(coords)*e1 - e1.jacobian(coords)*e2)
assert nabla(s.Matrix([1,0]), V) == s.zeros(2,1)
assert nabla(s.Matrix([0,1]), V) == s.zeros(2,1)
assert nabla(e1,e2)-nabla(e2,e1) == s.Matrix([0,-1/r**2])
assert nabla(e1,e2)-nabla(e2,e1)-bracket == s.zeros(2,1)

u,v = s.symbols('u v', real=True)
surface = s.Matrix([u+v,v,((u+v)**2+2*v*v)/2])
J = surface.jacobian([u,v])
g0 = (J.T*J).subs({u:0,v:0})
n = s.simplify(J[:,0].cross(J[:,1]))
n = s.simplify(n / s.sqrt(n.dot(n)))
b0 = s.Matrix(2,2,lambda i,j: n.dot(surface.diff([u,v][i],[u,v][j]))).subs({u:0,v:0})
S = g0.inv()*b0
assert S == s.Matrix([[1,-1],[0,2]])
assert S.T*g0 == g0*S
assert S.T != S
assert S*s.Matrix([1,0]) == s.Matrix([1,0])
assert S*s.Matrix([-1,1]) == 2*s.Matrix([-1,1])

# Right spherical triangle: N -> A=(1,0,0) -> B=(0,1,0) -> N.
# Along each great circle, parallel transport is the ambient rotation taking
# the starting point to the endpoint about the oriented great-circle axis.
N,A,B = s.Matrix([0,0,1]),s.Matrix([1,0,0]),s.Matrix([0,1,0])


def cross_matrix(axis):
    x,y,z=axis
    return s.Matrix([[0,-z,y],[z,0,-x],[-y,x,0]])


def quarter_turn(p,q):
    axis=p.cross(q)
    return axis*axis.T+cross_matrix(axis)


transport = quarter_turn(B,N)*quarter_turn(A,B)*quarter_turn(N,A)
assert transport*N == N
assert transport*s.Matrix([1,0,0]) == s.Matrix([0,1,0])

# The first completed chapter uses an arbitrary equatorial angle alpha.
alpha=s.symbols('alpha', real=True)
B_alpha=s.Matrix([s.cos(alpha),s.sin(alpha),0])
Rz=s.Matrix([[s.cos(alpha),-s.sin(alpha),0], [s.sin(alpha),s.cos(alpha),0], [0,0,1]])
general_transport=s.simplify(quarter_turn(B_alpha,N)*Rz*quarter_turn(N,A))
assert s.simplify(general_transport-Rz) == s.zeros(3)

# Independent check of the latitude example in answer 02.
th,ph=s.symbols('th ph',real=True)
sphere=s.Matrix([s.sin(th)*s.cos(ph),s.sin(th)*s.sin(ph),s.cos(th)])
eth=sphere.diff(th)
eph=s.Matrix([-s.sin(ph),s.cos(ph),0])
def tangent_derivative(w):
    dw=w.diff(ph)
    return s.simplify(dw-sphere*dw.dot(sphere))
assert s.simplify(tangent_derivative(eth)-s.cos(th)*eph)==s.zeros(3,1)
assert s.simplify(tangent_derivative(eph)+s.cos(th)*eth)==s.zeros(3,1)
latitude_vector=s.sin(ph*s.cos(th))*eth+s.cos(ph*s.cos(th))*eph
assert tangent_derivative(latitude_vector)==s.zeros(3,1)
assert s.simplify(latitude_vector.subs({th:s.pi/3,ph:2*s.pi})+eph.subs(ph,0))==s.zeros(3,1)
assert s.simplify(latitude_vector.subs({th:s.pi/2,ph:2*s.pi})-eph.subs(ph,0))==s.zeros(3,1)

# Flat cone minus its apex: local curvature vanishes, global holonomy need not.
cone_alpha=s.symbols('cone_alpha',positive=True)
cone_g=s.diag(1,cone_alpha**2*r**2)
cone_gi=cone_g.inv()
cone_G=[[[s.simplify(sum(cone_gi[k,l]*(s.diff(cone_g[l,j],coords[i])+s.diff(cone_g[l,i],coords[j])-s.diff(cone_g[i,j],coords[l]))/2 for l in range(2))) for j in range(2)] for i in range(2)] for k in range(2)]
for l in range(2):
    for k in range(2):
        for i in range(2):
            for j in range(2):
                curvature=s.diff(cone_G[l][j][k],coords[i])-s.diff(cone_G[l][i][k],coords[j])+sum(cone_G[l][i][m]*cone_G[m][j][k]-cone_G[l][j][m]*cone_G[m][i][k] for m in range(2))
                assert s.simplify(curvature)==0
cone_J=s.Matrix([[0,-cone_alpha],[cone_alpha,0]])
cone_P=s.Matrix([[s.cos(cone_alpha*ph),s.sin(cone_alpha*ph)],[-s.sin(cone_alpha*ph),s.cos(cone_alpha*ph)]])
assert s.simplify(cone_P.diff(ph)+cone_J*cone_P)==s.zeros(2)
assert cone_P.subs({cone_alpha:s.Rational(1,2),ph:2*s.pi})==-s.eye(2)

# New examples and counterexamples from the book written without samples.
t=s.symbols('t',real=True)
helix_a=s.symbols('helix_a',positive=True)
helix_b=s.symbols('helix_b',real=True)
helix=s.Matrix([helix_a*s.cos(t),helix_a*s.sin(t),helix_b*t])
h1,h2,h3=helix.diff(t),helix.diff(t,2),helix.diff(t,3)
cross=h1.cross(h2)
speed_squared=s.simplify(h1.dot(h1))
kappa_squared=s.simplify(cross.dot(cross)/speed_squared**3)
tau=s.simplify(s.Matrix.hstack(h1,h2,h3).det()/cross.dot(cross))
assert s.simplify(kappa_squared-helix_a**2/(helix_a**2+helix_b**2)**2)==0
assert s.simplify(tau-helix_b/(helix_a**2+helix_b**2))==0
radius=s.symbols('radius',positive=True)
sphere_J=(radius*sphere).jacobian([th,ph])
sphere_metric=s.simplify(sphere_J.T*sphere_J)
assert sphere_metric==s.diag(radius**2,radius**2*s.sin(th)**2)
assert s.integrate(radius**2*s.sin(th),(th,0,s.pi),(ph,0,2*s.pi))==4*s.pi*radius**2
bad_chart=s.Matrix([u**3,v,0])
assert bad_chart.jacobian([u,v]).subs({u:0,v:0}).rank()==1
assert bad_chart[2]==0  # image is the ordinary xy-plane, with a unique tangent.
inflection=s.Matrix([t,t**3,0])
c1,c2=inflection.diff(t),inflection.diff(t,2)
inflection_kappa_squared=s.simplify(c1.cross(c2).dot(c1.cross(c2))/c1.dot(c1)**3)
assert inflection_kappa_squared.subs(t,0)==0
assert inflection_kappa_squared.subs(t,1)>0

result = {
    'polar_Gamma': {f'{k},{i},{j}': str(Gamma[k][i][j]) for k in range(2) for i in range(2) for j in range(2) if Gamma[k][i][j] != 0},
    'polar_constant_vector_derivatives': ['0','0'],
    'polar_frame_difference': str(nabla(e1,e2)-nabla(e2,e1)),
    'polar_frame_torsion': '0',
    'surface_g': str(g0), 'surface_b': str(b0), 'surface_S': str(S),
    'surface_eigenvalues': [str(x) for x in S.eigenvals()],
    'triangle_transport_matrix': str(transport),
    'general_triangle_transport_matrix': str(general_transport),
    'latitude_parallel_transport': 'verified by ambient differentiation and projection',
    'flat_cone_counterexample': 'all Riemann components zero; holonomy is -I for alpha=1/2',
    'no_examples_helix': {'kappa_squared':str(kappa_squared),'tau':str(tau)},
    'no_examples_sphere_metric':str(sphere_metric),
    'degenerate_parametrization_counterexample':'(u^3,v,0): rank 1 at origin; image is the xy-plane',
    'zero_point_curvature_counterexample':str(inflection_kappa_squared),
    'assertions': 'passed',
}
out = Path(__file__).with_name('math-checks.json')
out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False, indent=2))
