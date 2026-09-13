"""Euler–Bernoulli cantilever; N, mm, MPa. Downward displacement is positive."""
from dataclasses import dataclass, replace

@dataclass(frozen=True)
class Beam:
    force: float = 200
    length: float = 1000
    width: float = 20
    height: float = 40
    young: float = 200000

    @property
    def inertia(self):
        return self.width*self.height**3/12

    @property
    def section_modulus(self):
        return self.inertia/(self.height/2)

    def moment(self, x):
        return -self.force*(self.length-x)

    def stress(self, x, y):
        # y positive upward; hogging moment => upper fibres in tension.
        return -self.moment(x)*y/self.inertia

    def deflection(self, x):
        return self.force*x*x*(3*self.length-x)/(6*self.young*self.inertia)

    @property
    def tip(self):
        return self.deflection(self.length)

    @property
    def max_stress(self):
        return self.stress(0,self.height/2)

BASE = Beam()

def validate():
    import math
    close = lambda a,b: math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-10)
    assert close(BASE.inertia,106666.66666666667)
    assert close(BASE.max_stress,37.5)
    assert close(BASE.tip,3.125)
    assert BASE.deflection(0) == 0 and BASE.moment(BASE.length) == 0
    assert BASE.stress(0,0) == 0 and BASE.stress(0,-20) == -37.5
    for field, delta_ratio, stress_ratio in [("force",2,2),("length",8,2),("width",.5,.5),("height",.125,.25)]:
        other=replace(BASE,**{field:getattr(BASE,field)*2})
        assert close(other.tip/BASE.tip,delta_ratio)
        assert close(other.max_stress/BASE.max_stress,stress_ratio)
    return {"I_mm4":BASE.inertia,"W_mm3":BASE.section_modulus,"moment_Nm":abs(BASE.moment(0))/1000,"stress_MPa":BASE.max_stress,"deflection_mm":BASE.tip,"scaling_checks":"passed"}

if __name__ == "__main__":
    print(validate())
