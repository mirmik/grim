"""Geometry in chapter coordinates; S = -dn and upward graph normals."""
import numpy as np

def graph(x, y, a=1., b=3.):
    return np.array([x, y, .5*(a*x*x+b*y*y)])

def normal(x, y, a=1., b=3.):
    v=np.array([-a*x, -b*y, 1.])
    return v/np.linalg.norm(v)

def section(theta, t, a=1., b=3.):
    return graph(t*np.cos(theta), t*np.sin(theta), a, b)

def curvature(theta, a=1., b=3.):
    return a*np.cos(theta)**2+b*np.sin(theta)**2

def sheet(x, y, bend):
    if abs(bend)<1e-8:return np.array([x,y,0.])
    return np.array([np.sin(bend*x)/bend,y,(np.cos(bend*x)-1)/bend])

def sheet_normal(x, bend):
    return np.array([np.sin(bend*x),0.,np.cos(bend*x)])

def validate():
    h=1e-5
    for a,b in [(1,3),(1,-1)]:
        for theta in np.linspace(0,2*np.pi,71):
            w=np.array([np.cos(theta),np.sin(theta),0.])
            dn=(normal(*(h*w[:2]),a,b)-normal(*(-h*w[:2]),a,b))/(2*h)
            kn=-np.dot(dn,w)
            assert abs(kn-curvature(theta,a,b))<2e-8
            acceleration=(section(theta,h,a,b)+section(theta,-h,a,b))/(h*h)
            assert abs(acceleration[2]-kn)<2e-8
            assert abs(dn[2])<1e-12
    for bend in [0,.4,1.25]:
        for x in np.linspace(-1.2,1.2,19):
            du=(sheet(x+h,.1,bend)-sheet(x-h,.1,bend))/(2*h)
            dv=(sheet(x,.1+h,bend)-sheet(x,.1-h,bend))/(2*h)
            n=sheet_normal(x,bend)
            assert np.allclose([du@du,du@dv,dv@dv,n@du,n@dv],[1,0,1,0,0],atol=1e-9)
            dn=(sheet_normal(x+h,bend)-sheet_normal(x-h,bend))/(2*h)
            assert abs(-dn@du+bend)<1e-9
    assert abs(curvature(np.pi/4)-2)<1e-12
    # Same second form in a non-orthonormal basis: b alone has wrong eigenvalues.
    change=np.diag([2.,3.]);g=change.T@change;b=change.T@np.diag([1.,3.])@change
    assert np.allclose(np.linalg.eigvals(np.linalg.solve(g,b)),[1,3])
    return dict(normal_derivative_and_section='passed',euler_formula='passed',
                cylinder_metric_and_signed_curvature='passed',coordinate_operator='passed')

if __name__=='__main__':print(validate())
