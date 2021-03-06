# -*- coding: utf-8 -*-
"""
Created on Wed Jun 12 17:17:59 2019 by Andrea
Last modified jan 17 2020 by Sandrine
"""

import numpy as np
from scipy.integrate import odeint
import collections


class FlatPlateModel:
    
    def __init__(self,initialconditions,finalposition,config):
        
        self.config = config
        
        self.xA = initialconditions[0]
        self.yA = initialconditions[1]
        self.A = np.array([self.xA,self.yA])
        self.uA = initialconditions[2]
        self.vA = initialconditions[3]
        self.xB = finalposition[0]
        self.yB = finalposition[1]
        self.B = np.array([self.xB,self.yB])
        self.rhoAB = np.linalg.norm(self.A-self.B)
        self.diffyAB_init = abs(self.yA-self.yB)

        self.threshold_angle = 10

        self.BA = self.A-self.B
        self.phiA = np.arctan2(self.BA[1],self.BA[0])

        self.Drag = 0                                   #not considering drag forces
        self.c = 0.1                                    #flat plate chord
        self.L = 1                                      #flat plate length
        self.t = 0.01                                   #flat plate thickness
        self.S = self.c*self.L
        self.rho_plate = 0.5*2                          #flat plate density (paper of 500g/m^2 density)
        self.m = self.rho_plate*self.L*self.c*self.t    #flate plate mass
        self.rho_air = 1.18415
        self.mr = (self.rho_air*self.S*np.pi)/self.m
        self.g = -9.806                                 #gravity taking into account the reference system
        
        self.cartesian_init = np.array([self.xA,self.yA, self.uA, self.vA])
        self.state = self.get_state_in_relative_polar_coordinates(self.cartesian_init)

        action_space = collections.namedtuple('action_space', ['low', 'high'])(-15/180*np.pi, 15/180*np.pi)
        action_size = 1
        state_size = self.state.shape[0]

        self.nb_ep = 0
        self.nb_pointB_change =0

        self.B_array = np.zeros([self.config["MAX_EPISODES"]//self.config["POINTB_CHANGE"]+1, 2])
        self.B_array[self.nb_pointB_change, :] = self.B
    
        self.var_episode = [0]
        self.variables = ['x', 'y', 'u', 'v', 'actions', 'rewards']
        self.dt_array = np.array([i*config["DELTA_TIME"] for i in range(config["MAX_STEPS"]+1)])
        self.var_array = np.zeros([len(self.variables), config["MAX_EPISODES"],config["MAX_STEPS"]+1])
        # fill array with initial state
        for i in range(len(self.cartesian_init)):
            self.var_array[i,:,0] = self.cartesian_init[i]
 
    #compute next state, reward and done or not
    def step(self,action):
        #alpha is the action
        self.alpha = action
        old_polar_state = self.state
        #if some noise is wanted to be added to 'model' turbulence effects
        self.alpha = action + np.random.normal(scale=self.config["ACTION_SIGMA"])
        
        #time vector with initial and final point of the step
        timearray=np.linspace(0,self.config["DELTA_TIME"],2)
        old_cartesian_state = self.get_state_in_absolute_cartesian_coordinates(old_polar_state)
        #y = odeint(model, y0, t)
        odestates = odeint(self.flatplate,old_cartesian_state,timearray)
        #as odeint will return two different states, choose the second one
        new_cartesian_state = odestates[-1]
        new_polar_state = self.get_state_in_relative_polar_coordinates(new_cartesian_state)
        self.state = new_polar_state
        
        reward = self.compute_reward(old_polar_state, action, new_polar_state)
        done = self.isdone(new_polar_state)

        # save data for printing
        self.var_episode.append([new_cartesian_state[0], new_cartesian_state[1], new_cartesian_state[2], new_cartesian_state[3], self.alpha/np.pi*180, reward])
        
        return [self.state, reward, done]


    def reset(self, state=None):
        if state==None:
            self.state = self.get_state_in_relative_polar_coordinates(self.cartesian_init)
        else:
            self.state = state

        self.nb_ep +=1
        self.var_episode = []
        if np.mod(self.nb_ep,self.config["POINTB_CHANGE"]) == 0:
            self.update_B()

        return self.state


    # differential equations system for flat plate
    def flatplate(self, polar_state, t):
        cartesian_state = self.get_state_in_absolute_cartesian_coordinates(polar_state)
        u = cartesian_state[2]
        v = cartesian_state[3]
        
        V = np.sqrt(u**2+v**2)
        alphainduced = np.arctan2(v,u)
        # TO DO check
        if alphainduced <= np.pi and alphainduced >= 0:
            alphainduced = -(np.pi - np.abs(alphainduced))
        else:
            alphainduced = np.pi - np.abs(alphainduced)
        
        dxdt = u
        dydt = v
        
        dudt = self.Drag/self.m 
        dvdt = self.g + self.mr * V**2 * (self.alpha + alphainduced) 
        
        computedstate = np.array([dxdt, dydt, dudt, dvdt])
        return computedstate


    def compute_reward(self, old_polar_state, action, new_polar_state):
        delta_rho = new_polar_state[0] - old_polar_state[0]
        delta_abs_theta = np.abs(new_polar_state[1]) - np.abs(old_polar_state[1])
        #reward = -10000*delta_rho # go to goal
        reward = -10000*delta_rho -1 # go to goal through the shortest path
        #reward = -delta_rho - delta_abs_theta # go to goal along the AB line

        return reward

    
    def isdone(self, polar_state):
        done = False
        #done if the final point is almost reached or if abs(theta) >= pi/2
        if np.abs(polar_state[0]/self.rhoAB) <= 10**(-3) or np.abs(polar_state[1]+self.phiA) >= np.pi/2.:
            done = True
        return done
    

    def get_state_in_relative_polar_coordinates(self, cartesian_state):
        BP = cartesian_state[0:2]-self.B
        rho = np.linalg.norm(BP)
        phiP = np.arctan2(BP[1],BP[0])
        theta = phiP - self.phiA

        u = cartesian_state[2]
        v = cartesian_state[3]

        rhoDot = u * np.cos(phiP) + v * np.sin(phiP)
        thetaDot = - u * np.sin(phiP) + v * np.cos(phiP)
        polar_state = np.array([rho, theta, rhoDot, thetaDot])

        return polar_state


    def get_state_in_absolute_cartesian_coordinates(self, polar_state):
        rho = polar_state[0]
        theta = polar_state[1]
        rhoDot = polar_state[2]
        thetaDot = polar_state[3]
        phiP = theta + self.phiA

        x = self.xB + rho * np.cos(phiP)
        y = self.yB + rho * np.sin(phiP)

        u = rhoDot * np.cos(phiP) - thetaDot * np.sin(phiP)
        v = rhoDot * np.sin(phiP) + thetaDot * np.cos(phiP)
        cartesian_state = np.array([x, y, u, v])

        return cartesian_state


    # update B coordinates as required in the CFD config file
    def update_B(self):
        self.nb_pointB_change +=1

        self.xB = np.random.uniform(self.xA, self.config["XB"])
        self.yB = np.random.uniform(self.yA-self.diffyAB_init, self.yA+self.diffyAB_init)

        # keep iterating until the absolute angle between A and B is below 10 degrees
        while abs(np.arctan2(abs(self.yB-self.yA),abs(self.xB-self.xA))) > self.threshold_angle*np.pi/180:
            self.xB = np.random.uniform(self.xA, self.config["XB"])
            self.yB = np.random.uniform(self.yA-self.diffyAB_init, self.yA+self.diffyAB_init)

        print('Final absolute angle',abs(np.arctan2(abs(self.yB-self.yA),abs(self.xB-self.xA)))/np.pi*180)
        print('Final point coordinates: (',self.xB,self.yB,')')

        self.B = np.array([self.xB,self.yB])
        self.rhoAB = np.linalg.norm(self.A-self.B)
        self.BA = self.A-self.B
        self.phiA = np.arctan2(self.BA[1],self.BA[0])
        
        self.B_array[self.nb_pointB_change, :] = self.B 
        #print(self.B_array)


    def fill_array_tobesaved(self):
        for i in range(len(self.variables)):
            for k in range(len(self.var_episode)):
                self.var_array[i, self.nb_ep-1, k+1] = self.var_episode[k][i]
        #print(self.var_array)


    def print_arrays_in_file(self, folder):
        for i, var in enumerate(self.variables):
            filename = folder+'/'+var+'.csv'
            np.savetxt(filename, self.var_array[i,:,:], delimiter=";")
 
        filename = folder+'/Bcoordinates.csv'
        np.savetxt(filename, self.B_array, delimiter=";")

        filename = folder+'/time.csv'
        np.savetxt(filename, self.dt_array, delimiter=";")
