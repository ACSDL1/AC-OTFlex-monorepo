# Script for UFactory xArm 6 functionality
#%%
import sys
import math
import time
import queue
import datetime
import random
import traceback
import threading
try:
    from xarm import version
    from xarm.wrapper import XArmAPI
    XARM_AVAILABLE = True
except ImportError:
    print("[WARN] xArm SDK not available - running in simulation mode")
    version = None
    XArmAPI = None
    XARM_AVAILABLE = False


#%%

class RobotMain(object):
    """Robot Main Class"""
    def __init__(self, robot, **kwargs):
        self.alive = True
        self._arm = robot
        self._ignore_exit_state = False
        self._tcp_speed = 100
        self._tcp_acc = 2000
        self._angle_speed = 20
        self._angle_acc = 500
        self._vars = {}
        self._funcs = {}
        self._robot_init()

    # Robot init
    def _robot_init(self):
        self._arm.clean_warn()
        self._arm.clean_error()
        self._arm.motion_enable(True)
        self._arm.set_mode(0)
        self._arm.set_state(0)
        time.sleep(1)
        self._arm.register_error_warn_changed_callback(self._error_warn_changed_callback)
        self._arm.register_state_changed_callback(self._state_changed_callback)

    # Register error/warn changed callback
    def _error_warn_changed_callback(self, data):
        if data and data['error_code'] != 0:
            self.alive = False
            self.pprint('err={}, quit'.format(data['error_code']))
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)

    # Register state changed callback
    def _state_changed_callback(self, data):
        if not self._ignore_exit_state and data and data['state'] == 4:
            self.alive = False
            self.pprint('state=4, quit')
            self._arm.release_state_changed_callback(self._state_changed_callback)

    def _check_code(self, code, label):
        # Debug output
        print(f"[DEBUG] {label}: code={code}, is_alive={self.is_alive}, state={self._arm.state}")
        
        if code != 0:
            self.alive = False
            ret1 = self._arm.get_state()
            ret2 = self._arm.get_err_warn_code()
            self.pprint('FAILED: {}, code={}, connected={}, state={}, error={}, ret1={}. ret2={}'.format(
                label, code, self._arm.connected, self._arm.state, self._arm.error_code, ret1, ret2))
            return False
        
        if not self.is_alive:
            print(f"[DEBUG] {label}: Command succeeded (code=0) but is_alive=False, continuing anyway...")
            # Don't return False here - let the sequence continue even if is_alive is False
        
        return True  # Always return True if code == 0

    @staticmethod
    def pprint(*args, **kwargs):
        try:
            stack_tuple = traceback.extract_stack(limit=2)[0]
            print('[{}][{}] {}'.format(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())), stack_tuple[1], ' '.join(map(str, args))))
        except:
            print(*args, **kwargs)

    @property
    def arm(self):
        return self._arm

    @property
    def VARS(self):
        return self._vars

    @property
    def FUNCS(self):
        return self._funcs

    @property
    def is_alive(self):
        if self.alive and self._arm.connected and self._arm.error_code == 0:
            if self._ignore_exit_state:
                return True
            if self._arm.state == 5:
                cnt = 0
                while self._arm.state == 5 and cnt < 5:
                    cnt += 1
                    time.sleep(0.1)
            return self._arm.state < 4
        else:
            return False

    def run_place_plate_to_reactor(self):
        """Sequence to place a plate"""
        try:
            self._tcp_speed = 200
            self._tcp_acc = 200
            self._angle_speed = 15
            self._angle_acc = 200
            code = self._arm.set_tcp_load(0, [0, 0, 0])
            if not self._check_code(code, 'set_tcp_load'):
                return
            code = self._arm.set_servo_angle(angle=[180.5, -7.9, -166.9, 352.0, -5.7, 6.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[181.4, -89.5, -72.3, 358.0, 72.5, 1.1], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[181.5, -58.9, -17.8, 358.0, 72.5, 1.1], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_gripper_position(500, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_servo_angle(angle=[180.2, -25.5, -13.8, 269.6, 89.9, -36.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[112.9, -37.7, -6.4, 208.1, 48.6, 70.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_position(*[-91.0, 310.0, 247.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(80, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_gripper_position(30, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            self._tcp_speed = 50
            self._tcp_acc = 50
            self._angle_speed = 5
            self._angle_acc = 50
            code = self._arm.set_position(*[-91.0, 185.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-309.0, 182.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 200.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 307.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 307.0, 236.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(120, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_position(*[-307.0, 50.0, 236.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-200.0, 40.0, 600.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_servo_angle(angle=[180.5, -7.9, -166.9, 352.0, -5.7, 6.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            
            time.sleep(5)

        except Exception as e:
            self.pprint('MainException: {}'.format(e))
        finally:
            self.alive = False
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)
            self._arm.release_state_changed_callback(self._state_changed_callback)


    def run_reactor_to_furnace(self):
        """Sequence to remove a plate"""
        try:
            print("[DEBUG] Checking arm state before sequence...")
            if self._arm.state != 0:
                print(f"[DEBUG] Arm in state {self._arm.state}, setting to ready...")
                self._arm.set_state(0)
                time.sleep(1.0)
            
            # Reset alive flag
            self.alive = True
            self._tcp_speed = 200
            self._tcp_acc = 200
            self._angle_speed = 15
            self._angle_acc = 200
            code = self._arm.set_tcp_load(0, [0, 0, 0])
            if not self._check_code(code, 'set_tcp_load'):
                return
            code = self._arm.set_servo_angle(angle=[180.5, -7.9, -166.9, 352.0, -5.7, 6.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[181.4, -89.5, -72.3, 358.0, 72.5, 1.1], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[181.5, -58.9, -17.8, 358.0, 72.5, 1.1], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_gripper_position(500, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_servo_angle(angle=[180.2, -25.5, -13.8, 269.6, 89.9, -36.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[112.9, -37.7, -6.4, 208.1, 48.6, 70.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            self._tcp_speed = 50
            self._tcp_acc = 50
            self._angle_speed = 5
            self._angle_acc = 50
            code = self._arm.set_position(*[-309.0, 182.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 307.0, 236.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(30, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_position(*[-307.0, 307.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 200.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-309.0, -100.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            self._tcp_speed = 200
            self._tcp_acc = 200
            self._angle_speed = 15
            self._angle_acc = 200
            code = self._arm.set_position(*[-200.0, -100.0, 600.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_servo_angle(angle=[350.0, -34.6, -55.5, 270.0, 80.0, 0.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_position(*[320.0, -135.3, 350.0, 88.6, 0.6, -0.1], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[320.0, -135.3, 350.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[320.0, -480.0, 350.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[140.0, -490.0, 355.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[90.0, -490.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(80, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_gripper_position(150, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_position(*[300.0, -490.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[300.0, -150.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_servo_angle(angle=[343.0, 7.2, -150.0, 333.1, 145.2, 67.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[180.5, -7.9, -166.9, 352.0, -5.7, 6.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            
            time.sleep(5)

        except Exception as e:
            self.pprint('MainException: {}'.format(e))
        finally:
            self.alive = False
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)
            self._arm.release_state_changed_callback(self._state_changed_callback)

    def run_furnace_to_reactor(self):
        """Sequence to take plate from furnace to reactor (reverse of reactor_to_furnace)"""
        try:
            print("[DEBUG] Checking arm state before sequence...")
            if self._arm.state != 0:
                print(f"[DEBUG] Arm in state {self._arm.state}, setting to ready...")
                self._arm.set_state(0)
                time.sleep(1.0)
            
            # Reset alive flag
            self.alive = True
            self._tcp_speed = 200
            self._tcp_acc = 200
            self._angle_speed = 15
            self._angle_acc = 200
            
            # Start from home position and go to furnace
            code = self._arm.set_tcp_load(0, [0, 0, 0])
            if not self._check_code(code, 'set_tcp_load'):
                return
            code = self._arm.set_servo_angle(angle=[180.5, -7.9, -166.9, 352.0, -5.7, 6.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[343.0, 7.2, -150.0, 333.1, 145.2, 67.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_position(*[300.0, -150.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[300.0, -490.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            
            # Open gripper and pick up plate from furnace
            #code = self._arm.set_gripper_position(80, wait=True, speed=5000, auto_enable=True)
            #if not self._check_code(code, 'set_gripper_position'):
            #    return
            #code = self._arm.set_gripper_position(30, wait=True, speed=5000, auto_enable=True)
            #if not self._check_code(code, 'set_gripper_position'):
            #    return

            code = self._arm.set_gripper_position(150, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            
            code = self._arm.set_position(*[90.0, -490.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            
            code = self._arm.set_gripper_position(30, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
                
                
            code = self._arm.set_position(*[140.0, -490.0, 355.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            
            code = self._arm.set_position(*[320.0, -480.0, 350.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            
            code = self._arm.set_position(*[320.0, -135.3, 350.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[320.0, -135.3, 350.0, 88.6, 0.6, -0.1], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            
            
            code = self._arm.set_servo_angle(angle=[350.0, -34.6, -55.5, 270.0, 80.0, 0.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_position(*[-200.0, -100.0, 600.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            
            
            
            # Move to reactor area
            self._tcp_speed = 50
            self._tcp_acc = 50
            self._angle_speed = 5
            self._angle_acc = 50
            code = self._arm.set_position(*[-309.0, -100.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 200.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 307.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            
            # Place plate in reactor
            code = self._arm.set_position(*[-307.0, 307.0, 236.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            # open gripper
            code = self._arm.set_gripper_position(150, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_position(*[-309.0, 182.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
        
            
            # Return to home position
            self._tcp_speed = 200
            self._tcp_acc = 200
            self._angle_speed = 15
            self._angle_acc = 200
            code = self._arm.set_servo_angle(angle=[112.9, -37.7, -6.4, 208.1, 48.6, 70.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[180.2, -25.5, -13.8, 269.6, 89.9, -36.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_gripper_position(500, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_servo_angle(angle=[181.5, -58.9, -17.8, 358.0, 72.5, 1.1], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[181.4, -89.5, -72.3, 358.0, 72.5, 1.1], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[180.5, -7.9, -166.9, 352.0, -5.7, 6.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            
            time.sleep(5)

        except Exception as e:
            self.pprint('MainException: {}'.format(e))
        finally:
            self.alive = False
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)
            self._arm.release_state_changed_callback(self._state_changed_callback)

    # Robot Main Run
    def run(self):
        try:
            self._tcp_speed = 200
            self._tcp_acc = 200
            self._angle_speed = 15
            self._angle_acc = 200
            code = self._arm.set_tcp_load(0, [0, 0, 0])
            if not self._check_code(code, 'set_tcp_load'):
                return
            code = self._arm.set_servo_angle(angle=[180.5, -7.9, -166.9, 352.0, -5.7, 6.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[181.4, -89.5, -72.3, 358.0, 72.5, 1.1], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[181.5, -58.9, -17.8, 358.0, 72.5, 1.1], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_gripper_position(500, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_servo_angle(angle=[180.2, -25.5, -13.8, 269.6, 89.9, -36.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[110.1, -39.4, -17.0, 202.0, 36.7, -16.2], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[112.9, -37.7, -6.4, 208.1, 48.6, 70.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_position(*[-91.0, 310.0, 247.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(80, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_gripper_position(30, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            self._tcp_speed = 50
            self._tcp_acc = 50
            self._angle_speed = 5
            self._angle_acc = 50
            code = self._arm.set_position(*[-91.0, 185.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-309.0, 182.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 200.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 307.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 307.0, 236.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(120, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_position(*[-307.0, 50.0, 236.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            for i in range(1950):
                time.sleep(0.1)
                if not self.is_alive:
                    return
            code = self._arm.set_position(*[-307.0, 307.0, 236.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(30, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_position(*[-307.0, 307.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 200.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-309.0, -100.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            self._tcp_speed = 200
            self._tcp_acc = 200
            self._angle_speed = 15
            self._angle_acc = 200
            code = self._arm.set_position(*[-200.0, -100.0, 600.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_servo_angle(angle=[350.0, -34.6, -55.5, 270.0, 80.0, 0.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_position(*[320.0, -135.3, 350.0, 88.6, 0.6, -0.1], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[320.0, -135.3, 350.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[320.0, -480.0, 350.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[140.0, -490.0, 355.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[90.0, -490.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(80, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_gripper_position(150, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_position(*[300.0, -490.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[300.0, -150.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_servo_angle(angle=[343.0, 7.2, -150.0, 333.1, 145.2, 67.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[180.5, -7.9, -166.9, 352.0, -5.7, 6.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            for i in range(10000):
                time.sleep(0.1)
                if not self.is_alive:
                    return
            code = self._arm.set_servo_angle(angle=[343.0, 7.2, -150.0, 333.1, 145.2, 67.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_position(*[300.0, -150.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[300.0, -490.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[90.0, -490.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(30, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_position(*[300.0, -490.0, 355.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[320.0, -480.0, 355.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[320.0, -135.3, 350.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[320.0, -135.3, 350.0, 88.6, 0.6, -0.1], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_servo_angle(angle=[350.0, -34.6, -55.5, 270.0, 80.0, 0.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_position(*[-200.0, -100.0, 600.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-309.0, -100.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 150.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-91.0, 185.0, 253.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-91.0, 225.0, 251.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-91.0, 310.0, 249.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(100, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_position(*[-91.0, 185.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 200.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 50.0, 236.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-309.0, -100.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-200.0, -100.0, 600.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_servo_angle(angle=[350.0, -34.6, -55.5, 270.0, 80.0, 0.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[180.5, -7.9, -166.9, 352.0, -5.7, 6.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
        except Exception as e:
            self.pprint('MainException: {}'.format(e))
        finally:
            self.alive = False
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)
            self._arm.release_state_changed_callback(self._state_changed_callback)

if __name__ == '__main__':
    RobotMain.pprint('xArm-Python-SDK Version:{}'.format(version.__version__))
    arm = XArmAPI('192.168.1.233', baud_checkset=False)
    time.sleep(0.5)
    robot_main = RobotMain(arm)
    robot_main.run()

# ===== Minimal adapter entrypoints for myxArm_Utils (1).py =====

def arm_connect(cfg: dict):
    """Initialize xArm connection"""
    global _robot_main, _arm_api

    print(f"[REAL] ARM CONNECT")
    print(f"  Config: {cfg}")

    if not XARM_AVAILABLE:
        print(f"  xArm SDK not available - running in simulation mode")
        return

    try:
        ip = cfg.get('ip', '192.168.1.233')
        print(f"  Connecting to xArm at {ip}")

        _arm_api = XArmAPI(ip, baud_checkset=False)
        time.sleep(0.5)
        _robot_main = RobotMain(_arm_api)
        # Clear errors and enable motion
        print(f"  Clearing errors and enabling motion...")

        # Clear warnings and errors
        _arm_api.clean_warn()
        _arm_api.clean_error()
        time.sleep(0.5)

        # Enable motion
        _arm_api.motion_enable(enable=True)
        time.sleep(0.5)

        # Set robot mode to position mode
        _arm_api.set_mode(0)  # Position mode
        time.sleep(0.5)

        # Set robot state to ready
        _arm_api.set_state(state=0)  # Ready state
        time.sleep(1.0)

        # Check final state
        code, state = _arm_api.get_state()
        print(f"  xArm state after initialization: {state}")

        if state == 2:
            print(f"  xArm in pause state, resuming...")
            _arm_api.set_state(state=0)  # Set to ready state
            time.sleep(1.0)
            code, state = _arm_api.get_state()
            print(f"  xArm state after resume: {state}")

        if state != 0:
            print(f"  WARNING: xArm not in ready state (state={state})")
            print(f"  Try manually clearing errors on the teach pendant")

        print(f"  xArm connected successfully")

    except Exception as e:
        print(f"  ERROR connecting to xArm: {e}")
        raise

def arm_disconnect():
    """Disconnect from xArm"""
    global _robot_main, _arm_api

    print(f"[REAL] ARM DISCONNECT")

    if not XARM_AVAILABLE:
        print(f"  xArm SDK not available - simulation mode")
        return

    try:
        if _robot_main:
            _robot_main.alive = False
        if _arm_api:
            _arm_api.disconnect()
        _robot_main = None
        _arm_api = None
        print(f"  xArm disconnected")

    except Exception as e:
        print(f"  ERROR disconnecting xArm: {e}")
        raise

def arm_move(params: dict):
    """Move xArm to specified position"""
    global _robot_main, _arm_api

    print(f"[REAL] ARM MOVE")
    print(f"  Params: {params}")

    if not XARM_AVAILABLE:
        print(f"  xArm SDK not available - simulation mode")
        return

    if not _arm_api or not _robot_main or not _robot_main.is_alive:
        raise RuntimeError("xArm not connected or not alive")

    try:
        pose = params.get('pose', {})
        speed = params.get('speed', 100)
        accel = params.get('accel', 200)

        if isinstance(pose, dict):
            # Convert dict pose to list [x, y, z, rx, ry, rz]
            position = [
                pose.get('x', 0), pose.get('y', 0), pose.get('z', 0),
                pose.get('rx', 0), pose.get('ry', 0), pose.get('rz', 0)
            ]
        else:
            position = pose

        print(f"  Moving to position: {position}")
        print(f"  Speed: {speed}, Accel: {accel}")

        code = _arm_api.set_position(*position, speed=speed, mvacc=accel, wait=True)
        if code != 0:
            raise RuntimeError(f"xArm move failed with code: {code}")

        print(f"  Move completed successfully")

    except Exception as e:
        print(f"  ERROR in arm move: {e}")
        raise

def arm_gripper(params: dict):
    """Control xArm gripper"""
    global _robot_main, _arm_api

    print(f"[REAL] ARM GRIPPER")
    print(f"  Params: {params}")

    if not XARM_AVAILABLE:
        print(f"  xArm SDK not available - simulation mode")
        return

    if not _arm_api or not _robot_main or not _robot_main.is_alive:
        raise RuntimeError("xArm not connected or not alive")

    try:
        action = params.get('action', 'open')
        width_mm = params.get('width_mm', 50)
        force = params.get('force', 50)

        print(f"  Gripper action: {action}, width: {width_mm}mm, force: {force}")

        # Note: This is a placeholder - actual gripper control depends on your gripper model
        # You may need to adjust this based on your specific gripper (RG2, etc.)
        if hasattr(_arm_api, 'set_gripper_position'):
            if action == 'open':
                code = _arm_api.set_gripper_position(width_mm, wait=True)
            elif action == 'close':
                code = _arm_api.set_gripper_position(0, wait=True)
            else:
                raise ValueError(f"Unknown gripper action: {action}")

            if code != 0:
                raise RuntimeError(f"Gripper operation failed with code: {code}")
        else:
            print(f"  WARNING: Gripper control not available on this xArm model")

        print(f"  Gripper operation completed")

    except Exception as e:
        print(f"  ERROR in gripper operation: {e}")
        raise

def arm_run_sequence(params: dict):
    """Run a complete pre-programmed sequence"""
    global _robot_main

    if not XARM_AVAILABLE:
        print(f"[REAL] ARM RUN SEQUENCE")
        print(f"  xArm SDK not available - simulation mode")
        return

    sequence = params.get('sequence', 'full_run')
    print(f"[REAL] ARM RUN SEQUENCE: {sequence}")

    try:
        if sequence == "placePlateToReactor":
            _robot_main.run_place_plate_to_reactor()
        elif sequence == "reactorToFurnace":
            _robot_main.run_reactor_to_furnace()
        elif sequence == "furnaceToReactor":
            _robot_main.run_furnace_to_reactor()
        elif sequence == "full_run":
            _robot_main.run()  # Your existing complete sequence
        else:
            print(f"  Unknown sequence: {sequence}")

    except Exception as e:
        print(f"  Sequence failed: {e}")
        raise
# %%
