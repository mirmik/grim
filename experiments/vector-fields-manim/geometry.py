"""Isometric cylinder unrolling and the two parts of an ambient derivative."""
import numpy as np


def sheet(s, z, bend):
    if abs(bend) < 1e-8:
        return np.array([s, 0., z])
    return np.array([np.sin(bend*s)/bend, (np.cos(bend*s)-1)/bend, z])


def frame(s, bend=1.):
    a = bend*s
    return np.array([np.cos(a), -np.sin(a), 0.]), np.array([0., 0., 1.]), np.array([np.sin(a), np.cos(a), 0.])


def field(s, beta=0., bend=1.):
    e, z, _ = frame(s, bend)
    return np.cos(beta)*e + np.sin(beta)*z


def derivative(s, beta=0., beta_prime=0., bend=1.):
    e, z, n = frame(s, bend)
    tangent = beta_prime*(-np.sin(beta)*e + np.cos(beta)*z)
    normal = -bend*np.cos(beta)*n
    return tangent + normal, tangent, normal


def validate():
    eps = 1e-5
    for k in [0., .01, .35, 1.]:
        for s in np.linspace(-np.pi, np.pi, 13):
            e, z, n = frame(s, k)
            jac = (sheet(s+eps, .2, k)-sheet(s-eps, .2, k))/(2*eps)
            np.testing.assert_allclose(jac, e, atol=1e-8)
            np.testing.assert_allclose(np.array([e,z,n])@np.array([e,z,n]).T, np.eye(3), atol=1e-12)
            beta = .5*(s+1.6)
            ambient, tangent, normal = derivative(s,beta,.5,k)
            finite = (field(s+eps,beta+.5*eps,k)-field(s-eps,beta-.5*eps,k))/(2*eps)
            np.testing.assert_allclose(ambient,finite,atol=1e-8)
            np.testing.assert_allclose(ambient-np.dot(ambient,n)*n,tangent,atol=1e-12)
            assert abs(np.dot(tangent,n))<1e-12
            np.testing.assert_allclose(derivative(s,0,0,k)[1],0,atol=1e-12)
    for a in np.linspace(0,np.pi/2,21):
        e1=np.array([np.cos(a),np.sin(a)])
        e2=np.array([-np.sin(a),np.cos(a)])
        np.testing.assert_allclose(np.cos(a)*e1-np.sin(a)*e2,[1,0],atol=1e-12)
    return dict(unrolling_preserves_metric=True, derivative_matches_finite_difference=True,
                projection_is_tangent=True, constant_cylinder_field_is_parallel=True,
                moving_basis_reconstructs_fixed_vector=True)


if __name__ == '__main__':
    print(validate())
