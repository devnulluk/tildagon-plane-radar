import math
import unittest
from radar_math import heading_vector, offset_km, radar_xy, rim_xy

class RadarMathTests(unittest.TestCase):
    def test_north_projects_up(self):
        x,y,distance=radar_xy(51.0,0.0,51.01,0.0,10.0,100.0); self.assertAlmostEqual(x,0.0,places=4); self.assertLess(y,0.0); self.assertGreater(distance,1.0)
    def test_east_projects_right(self):
        x,y,_=radar_xy(51.0,0.0,51.0,0.01,10.0,100.0); self.assertGreater(x,0.0); self.assertAlmostEqual(y,0.0,places=4)
    def test_heading_vectors_use_aviation_convention(self):
        dx,dy=heading_vector(0,10); self.assertAlmostEqual(dx,0.0,places=5); self.assertAlmostEqual(dy,-10.0,places=5); dx,dy=heading_vector(90,10); self.assertAlmostEqual(dx,10.0,places=5); self.assertAlmostEqual(dy,0.0,places=5)
    def test_rim_vector_keeps_direction(self):
        x,y=rim_xy(3.0,4.0,10.0); self.assertAlmostEqual(math.sqrt(x*x+y*y),10.0,places=5); self.assertGreater(x,0.0); self.assertLess(y,0.0)
    def test_offset_distance_is_symmetric_enough_for_local_radar(self):
        e1,n1,d1=offset_km(52.0,0.1,52.01,0.12); e2,n2,d2=offset_km(52.01,0.12,52.0,0.1); self.assertAlmostEqual(d1,d2,places=4); self.assertAlmostEqual(e1,-e2,places=4); self.assertAlmostEqual(n1,-n2,places=4)
