# -*- coding: utf-8 -*-

import os
import sys
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QSize, QRect
import numpy as np
import time

from threading import Thread, RLock
from functools import partial
from ctypes import *



class GroupCtrl(QGroupBox):
    def __init__(self, label='', parent=None):
        super().__init__(parent)
        self.setTitle(label)
        self.setStyleSheet(
            '''GroupCtrl{font-weight: bold; font-size:14pt}''')


class LVSpinBox(QDoubleSpinBox):
    ''' Custom SpinBox with similar properties as LabView number controls '''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setKeyboardTracking(False)
        self.setStyleSheet(
            '''LVSpinBox{qproperty-alignment:AlignCenter; font-size:10pt}''')

    def stepBy(self, step):
        value = self.value()
        minus = str(self.text()).find('-')
        cursor = self.lineEdit().cursorPosition()
        text = str(self.text())
        length = len(text)
        if minus > -1 and cursor == 0:
            return None
        point = text.find('.')
        if point < 0:
            point = length
        digit = point - cursor
        if cursor == minus + 1:
            digit -= 1
        if digit < -1:
            digit += 1
        self.setValue(value + step*(10**digit))
        # update the cursor position when the value changes
        newlength = len(str(self.text()))
        newcursor = cursor
        if newlength > length:
            if cursor == minus+1:
                newcursor = cursor + 2
            else:
                newcursor = cursor + 1
        elif newlength < length:
            if not cursor == minus+1:
                newcursor = cursor - 1
        else:
            return None
        self.lineEdit().setCursorPosition(newcursor)


class LVNumCtrl(QWidget):
    ''' Column alignment '''
    valueChanged = pyqtSignal(float)

    def __init__(self, label='', func=None, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.addStretch()
        if label != '':
            self.label = QLabel(label)
            self.label.setStyleSheet(
                '''QLabel{qproperty-alignment:AlignCenter; font-size:12pt}''')
            row.addWidget(self.label, 0)
        self.spin = LVSpinBox()
        self.spin.valueChanged.connect(self.valueChanged.emit)
        if func:
            self.valueChanged.connect(func)
        row.addWidget(self.spin, 1)
        row.addStretch()

    def setDecimals(self, decimals=0):
        self.spin.setDecimals(decimals)
        self.spin.adjustSize()

    def setRange(self, low=0, high=100):
        self.spin.setRange(low, high)
        self.spin.adjustSize()

    def value(self):
        if self.spin.decimals() == 0:
            return int(self.spin.value())
        else:
            return self.spin.value()

    def setValue(self, val):
        if val == self.spin.value():
            self.valueChanged.emit(val)
        else:
            self.spin.setValue(val)

    def setReadOnly(self, state):
        self.spin.setReadOnly(state)


class Button(QWidget):
    ''' Clickable button with label '''
    clicked = pyqtSignal(bool)

    def __init__(self, label='', func=None, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.addStretch()
        if label != '':
            self.label = QLabel(label)
            self.label.setStyleSheet(
                '''QLabel{qproperty-alignment:AlignCenter; font-size:12pt}''')
            row.addWidget(self.label, 0)
        self.button = QPushButton()
        row.addWidget(self.button, 1)
        row.addStretch()
        self.button.clicked.connect(self.clicked.emit)
        if func:
            self.clicked.connect(func)


class ButtonCtrl(QWidget):
    ''' Implemented button control with label and checkable property '''
    toggled = pyqtSignal(bool)

    def __init__(self, label='', func=None, default=False, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.addStretch()
        self.text = ('ON', 'OFF')
        if not label == '':
            self.label = QLabel(label)
            self.label.setStyleSheet(
                '''QLabel{qproperty-alignment:AlignCenter; font-size:12pt}''')
            row.addWidget(self.label, 0)
        self.button = QPushButton('ON')
        row.addWidget(self.button, 1)
        row.addStretch()
        # Defaultly False
        self.button.setCheckable(True)
        self.button.setStyleSheet(
            '''QPushButton{background-color:red; font-weight:bold; font-size: 10pt} QPushButton:checked{background-color: green}''')
        self.button.toggled.connect(self.toggled.emit)
        self.toggled.connect(self.updateStatus)
        if func:
            self.toggled.connect(func)
        self.button.setChecked(default)
        self.updateStatus(default)

    def setChecked(self, state):
        self.button.setChecked(state)

    def setStatusText(self, on='ON', off='OFF'):
        self.text = (on, off)
        self.updateStatus(self.button.isChecked())

    def isChecked(self):
        return self.button.isChecked()

    def updateStatus(self, state):
        if state:
            self.button.setText(self.text[0])
        else:
            self.button.setText(self.text[-1])


class AD5372Ctrl(GroupCtrl):
    '''The class DAC is a basic family for AD5732, which can be used to implement a shutter switch, a DC supply with \pm 10V, and a combination of multiple channnels'''

    def __init__(self, title='', parent=None):
        super().__init__(title, parent)
        self.dataFile = 'ad5372_data.dat'
        self.channelOrder = [1, 0, 3, 2, 5, 4, 7, 6, 9, 8, 11, 10, 13, 12, 15,
                             14, 17, 16, 19, 18, 21, 20, 23, 22, 25, 24, 27, 26, 29, 28, 31, 30]
        self.dataNum = 32
        self.createConfig()
        self.createChannels()
        # self.create_compensation()
        self.createShutters()
        self.createDCreferences()
        self.setupUI()
        self.loadData()

    def createChannels(self):
        self.channels = [LVNumCtrl(
            str(i+1), partial(self.dataUpdate, index=i)) for i in range(self.dataNum)]
        self.data = GroupCtrl(
            'DC Channels')
        gridLayout = QGridLayout(self.data)
        self.data.setContentsMargins(1, 1, 1, 1)
        
        # DC Bias
        self.dc_bias_up = LVNumCtrl("Bias UpUp", partial(self.applyBias, index=0))
        self.dc_bias_up.setDecimals(4)

        self.dc_bias_down = LVNumCtrl("Bias Down", partial(self.applyBias, index=1))
        self.dc_bias_down.setDecimals(4)

        # RF Bias
        self.rf_bias_up = self.channels[10]
        self.rf_bias_up.setDecimals(4)

        self.rf_bias_down = self.channels[11]
        self.rf_bias_down.setDecimals(4)

        # set layout
        # up dc
        """
        for i in range(4):
            self.channels[i].setDecimals(4)
            self.channels[i].setRange(-10.0, 10.0)
        """
        # Data entries
        # DC Up configuration
        gridLayout.addWidget(QLabel("DC UpUp"),0,0,1,1)
        gridLayout.addWidget(self.dc_bias_up,0,6,1,1)
        for i in range(5):
            self.channels[i].setDecimals(4)
            self.channels[i].setRange(-10.0, 10.0)
            gridLayout.addWidget(self.channels[i],0,i%5+1,1,1)

        # DC down configuration
        gridLayout.addWidget(QLabel("DC Down"),1,0,1,1)
        gridLayout.addWidget(self.dc_bias_down,1,6,1,1)
        for i in range(5,10):
            self.channels[i].setDecimals(4)
            self.channels[i].setRange(-10.0, 10.0)
            gridLayout.addWidget(self.channels[i],1,i%5+1,1,1)

        # RF bias configuration
        gridLayout.addWidget(QLabel("RF UpUp"),2,1,1,1)
        gridLayout.addWidget(self.rf_bias_up,2,2,1,1)

        gridLayout.addWidget(QLabel("RF Down"),2,4,1,1)
        gridLayout.addWidget(self.rf_bias_down,2,5,1,1)    

        """
        for i in range(self.dataNum):
            self.channels[i].setDecimals(4)
            self.channels[i].setRange(-10.0, 10.0)
            # gridLayout.addWidget(QLabel("DC UP"))
            gridLayout.addWidget(self.channels[i], i//4, i % 4, 1, 1)
        """
        gridLayout.setContentsMargins(0, 0, 0, 0)
        gridLayout.setSpacing(0)
        gridLayout.setVerticalSpacing(0)

    """
    def create_compensation(self):
        '''This part is used to compensate the DC null to RF null'''
        names = ["Horizontal", "Vertical", "Axial", "DC1", "DC2", "RFs", "All"]
        self.compensationFrame = GroupCtrl(
            "Compensation Combinations: DC1 RF11 DC1-2 DC2-2")
        self.compensate = [[LVNumCtrl(names[i]), Button(
            'GO', partial(self.applyComp, num=i))] for i in range(len(names))]
        layout = QGridLayout(self.compensationFrame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.ratio = LVNumCtrl('Ratio')
        self.ratio.setDecimals(2)
        self.ratio.setRange(0, 50)
        self.ratio.setValue(1)
        layout.addWidget(self.ratio, 0, 0, 1, 1)
        for i in range(len(self.compensate)):
            group = QWidget()
            ly = QHBoxLayout(group)
            self.compensate[i][0].setRange(-1.0, 1.0)
            self.compensate[i][0].setDecimals(4)
            ly.addWidget(self.compensate[i][0], 1)
            ly.addWidget(self.compensate[i][1], 1)
            ly.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(group, (i+1)//4, (i+1) % 4, 1, 1)
    """
    def applyBias(self, index):
        # the dc up
        if index == 0:
            for i in range(5):
                self.chnnels[i].setValue(
                    self.chnnels[i].value() + self.dc_bias_up.value()
                )
        
        # the dc down
        if index == 1:
            for i in range(5,10):
                self.chnnels[i].setValue(
                    self.chnnels[i].value() + self.dc_bias_down.value()
                )

    """
    def applyComp(self, num):
        if num == 0:
            for i in range(5):
                self.channels[i].setValue(
                    self.channels[i].value() + self.compensate[num][0].value())
            self.channels[10].setValue(self.channels[10].value(
            ) + self.ratio.value()*self.compensate[num][0].value())
        elif num == 1:
            for i in range(5):
                self.channels[i].setValue(
                    self.channels[i].value() + self.compensate[num][0].value())
            self.channels[10].setValue(self.channels[10].value(
            ) - self.ratio.value()*self.compensate[num][0].value())
        elif num == 2:
            for i in (0, 5):
                self.channels[i].setValue(
                    self.channels[i].value() + self.compensate[num][0].value())
        elif num == 3:
            for i in range(5):
                self.channels[i].setValue(
                    self.channels[i].value() + self.compensate[num][0].value())
        elif num == 4:
            for i in range(5, 10):
                self.channels[i].setValue(
                    self.channels[i].value() + self.compensate[num][0].value())
        elif num == 5:
            for i in (10, 11):
                self.channels[i].setValue(
                    self.channels[i].value() + self.compensate[num][0].value())
        elif num == 6:
            for i in range(12):
                self.channels[i].setValue(
                    self.channels[i].value() + self.compensate[num][0].value())
    """
    def createShutters(self):
        self.shutterFrame = GroupCtrl('Shutters')
        # buttons = ['PMT', 'Protection', '399', '935', 'RF UnLock', 'Trap RF', '399']
        buttons = ['399', 'Protection', '935',"355"]

        self.shutterArray = [12,13,14,15]
        self.shutters = [ButtonCtrl(buttons[i], partial(
            self.switch, i)) for i in range(len(buttons))]
        layout = QHBoxLayout(self.shutterFrame)
        layout.setContentsMargins(0, 0, 0, 0)
        for i in range(len(buttons)):
            self.channels[self.shutterArray[i]-1].setReadOnly(True)
            self.channels[self.shutterArray[i]-1].valueChanged.connect(partial(self.updateShutter, num=i))
            layout.addWidget(self.shutters[i])

    def createDCreferences(self):
        self.dcreferencesFrame = GroupCtrl('DC References')
        gridLayout = QGridLayout(self.dcreferencesFrame)
        for i in range(16,32):
            self.channels[i].setDecimals(4)
            gridLayout.addWidget(self.channels[i],i//4-4,i%4,1,1)

    def createConfig(self):
        self.pre = QWidget()
        self.update = Button('Reset Board', self.reset)
        self.load = Button('Load Data', self.loadData)
        self.save = Button('Save Data', self.saveData)
        hlayout = QHBoxLayout(self.pre)
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.addWidget(self.update)
        hlayout.addWidget(self.load)
        hlayout.addWidget(self.save)

    def setupUI(self):
        layout = QVBoxLayout(self)
        layout.addWidget(self.pre)
        layout.addWidget(self.data)
        #layout.addWidget(self.compensationFrame)
        layout.addWidget(self.shutterFrame)
        layout.addWidget(self.dcreferencesFrame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setContentsMargins(1, 1, 1, 1)

    def set_shutter(self, num, state):
        '''API for shutter'''
        if num <= len(self.shutters):
            self.shutters[num-1].setChecked(state)
        else:
            print('Shutter index over range!')
            exit()

    def dataUpdate(self, value, index):
        self.set_voltage(
            self.channelOrder[index], value)

    def loadData(self):
        '''
            This function is used to load data from local data file, while the argument 'force_mode' is used to specify if all data will sent to the wifi server, otherwise we only change those whose value is different from the one imported from data file, which will generate a signal for the slot.
        '''
        self.openFile()
        exists = os.path.isfile(self.dataFile)
        if exists:
            data = np.loadtxt(self.dataFile)
            if not data.size == self.dataNum:
                print('data length is wrong!!!')
            for i in range(self.dataNum):
                self.channels[i].setValue(data[i])                
                for i in range(len(self.shutters)):
                    self.updateShutter(i)
        else:
            np.savetxt(self.dataFile, np.zeros(self.dataNum))
            self.reset()

    def openFile(self):
        options = QFileDialog.Options()
        options = QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Load Data File", "", "Data File(*.dat)", options=options)
        if file_name:
            self.dataFile = file_name
    
    def saveFile(self):
        options = QFileDialog.Options()
        options = QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save Data File", "", "Data File(*.dat)", options=options)
        if file_name:
            self.dataFile = file_name + '.dat'
            print(self.dataFile)
                
    def saveData(self):
        self.saveFile()
        data = np.array([self.channels[i].value()
                         for i in range(self.dataNum)])
        np.savetxt(self.dataFile, data)

    def reset(self):
        for i in range(self.dataNum):
            self.channels[i].setValue(0.0)


    def updateShutter(self, num):
        if abs(self.channels[self.shutterArray[num] - 1].value()) < 0.1:
            self.shutters[num].setChecked(False)
        elif abs(self.channels[self.shutterArray[num] - 1].value() - 5) < 0.1:
            self.shutters[num].setChecked(True)
        else:
            if self.shutters[num].isChecked():
                self.shutters[num].setChecked(False)
            else:
                self.channels[self.shutterArray[num]-1].setValue(0)

    def switch(self, index, state):
        if state:
            self.channels[self.shutterArray[index]-1].setValue(5)
        else:
            self.channels[self.shutterArray[index]-1].setValue(0.0)

    def set_voltage(self, channel, Vout):
        if (abs(Vout) > 10.00001):
            print('Voltage over range!')
            return




class Window(QWidget):
    def __init__(self):
        super().__init__()
        # self.setWindowIcon(QIcon('control-panel.png'))
        self.setWindowIconText('Control Panel')
        self.dac = AD5372Ctrl('AD5372')
        col = QVBoxLayout(self)
        col.setSpacing(0)
        col.addWidget(self.dac)



        
        self.setContentsMargins(1, 1, 1, 1)
        self.setWindowTitle('Control Panel')


    def center(self):
        frame_geometry = self.frameGeometry()
        screen = QApplication.desktop().screenNumber(
            QApplication.desktop().cursor().pos())
        center_point = QApplication.desktop().screenGeometry(screen).center()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())


if __name__ == '__main__':
    myappid = u'PyControl'  # arbitrary string
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    app = QApplication(sys.argv)
    app.setFont(QFont('Vollkorn', 10))
    app.setStyle('Fusion')
    # app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    ui = Window()
    ui.center()
    ui.show()
    sys.exit(app.exec_())
