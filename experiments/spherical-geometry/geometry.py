"""Unit-sphere geometry; transport is an exact rotation on each great-circle arc."""
import math
import numpy as np

N = np.array([0., 0., 1.])
A = np.array([1., 0., 0.])

def unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)

def rotate(v, axis, angle):
    axis = unit(axis)
    return v*math.cos(angle) + np.cross(axis,v)*math.sin(angle) + axis*np.dot(axis,v)*(1-math.cos(angle))

def arc(a,b,u):
    angle = math.acos(np.clip(np.dot(a,b),-1,1))
    return rotate(a,np.cross(a,b),angle*u)

def vertices(phi=math.pi/2):
    return [N, A, np.array([math.cos(phi),math.sin(phi),0.]), N]

def transport(progress, phi=math.pi/2):
    """progress 0..3, one unit per side; retain vector at corners."""
    verts = vertices(phi)
    v = A.copy()
    p = N.copy()
    for i,(a,b) in enumerate(zip(verts,verts[1:])):
        fraction = np.clip(progress-i,0,1)
        angle = math.acos(np.clip(np.dot(a,b),-1,1))*fraction
        axis = unit(np.cross(a,b))
        p = rotate(a,axis,angle)
        v = rotate(v,axis,angle)
        if progress <= i+1: break
    return p,v

def triangle_angle(a,b,c):
    u=unit(b-np.dot(a,b)*a)
    v=unit(c-np.dot(a,c)*a)
    return math.acos(np.clip(np.dot(u,v),-1,1))

def solid_angle(a,b,c):
    return 2*math.atan2(abs(np.linalg.det([a,b,c])),1+np.dot(a,b)+np.dot(b,c)+np.dot(c,a))

def cylinder(x,y,bend):
    """Isometric bend of a flat sheet: |dF/dx|=|dF/dy|=1, dot=0."""
    if bend < 1e-8: return np.array([x,y,0.])
    return np.array([math.sin(bend*x)/bend,y,(1-math.cos(bend*x))/bend])

def validate():
    max_tangent=max_norm=max_covariant=0.
    for phi in (math.pi/6,math.pi/3,math.pi/2):
        a,b,c,_=vertices(phi)
        angles=[triangle_angle(a,b,c),triangle_angle(b,c,a),triangle_angle(c,a,b)]
        assert abs(sum(angles)-math.pi-solid_angle(a,b,c))<1e-12
        assert abs(solid_angle(a,b,c)-phi)<1e-12
        p,v=transport(3,phi)
        assert np.linalg.norm(p-N)<1e-12
        assert np.linalg.norm(v-np.array([math.cos(phi),math.sin(phi),0.]))<1e-12
        for leg in range(3):
            for q in np.linspace(.01,.99,25):
                t=leg+q;p,v=transport(t,phi)
                max_tangent=max(max_tangent,abs(np.dot(p,v)))
                max_norm=max(max_norm,abs(np.linalg.norm(v)-1))
                h=1e-5
                derivative=(transport(t+h,phi)[1]-transport(t-h,phi)[1])/(2*h)
                covariant=derivative-np.dot(derivative,p)*p
                max_covariant=max(max_covariant,np.linalg.norm(covariant))
    assert max_tangent<1e-12 and max_norm<1e-12 and max_covariant<1e-8
    metric_error=0.
    for bend in (0.,.5,1.4):
        for x in np.linspace(-1.5,1.5,9):
            h=1e-5
            dx=(cylinder(x+h,0,bend)-cylinder(x-h,0,bend))/(2*h)
            dy=(cylinder(x,h,bend)-cylinder(x,-h,bend))/(2*h)
            metric_error=max(metric_error,abs(np.dot(dx,dx)-1),abs(np.dot(dy,dy)-1),abs(np.dot(dx,dy)))
    assert metric_error<1e-8
    return dict(octant_angles_degrees=[90,90,90],octant_solid_angle=math.pi/2,
                final_transport_degrees=90,angle_area_identity='passed for 30, 60, 90 degrees',
                maximum_tangency_error=max_tangent,maximum_vector_length_error=max_norm,
                maximum_covariant_derivative=max_covariant,cylinder_metric_error=metric_error)

if __name__=='__main__':
    import json
    print(json.dumps(validate(),indent=2))
