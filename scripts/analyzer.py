import os
import sys
import glob
import json
import argparse
import numpy as np
import seaborn as sns
import soundfile as sf
from scipy import signal
import scipy.fftpack as fftpack
import matplotlib.pyplot as plt

# local imports
from A_weighting import A_weighting

# TODO
# ------------------------
# maybe pad with zeros if it too short
# also need to consider finding the 1 second frame with the greatest energy

# Plot size
FIGSIZE = (15, 10)

# colors
COLOR1 = "#0B3C5D"
COLOR2 = "#328CC1"
COLOR3 = "#D9B310"
COLOR4 = "#1D2731" 

# font sizes
SMALL_SIZE = 14
MEDIUM_SIZE = 16
BIGGER_SIZE = 18
plt.rc('font', size=SMALL_SIZE)          # controls default text sizes
plt.rc('axes', titlesize=BIGGER_SIZE)    # fontsize of the axes title
plt.rc('axes', labelsize=MEDIUM_SIZE)    # fontsize of the x and y labels
plt.rc('xtick', labelsize=SMALL_SIZE)    # fontsize of the tick labels
plt.rc('ytick', labelsize=SMALL_SIZE)    # fontsize of the tick labels
plt.rc('legend', fontsize=SMALL_SIZE)    # legend fontsize

# plot title full names
test_names = {
    "30"   : "30km/hr",
    "20"   : "20km/hr",
    "10"   : "10km/hr",
    "stat" : "Stationary",
    "rev"  : "Reverse",
}

class Analyzer():
    
    def __init__(self, cal_file, cal_fs, cal_type, amb_file, output_dir, file_type, verbose=False):
        self.cal_file     = cal_file        # path to calibration nfile
        self.cal_fs       = cal_fs          # sampling rate of calibration file
        self.cal_type     = cal_type        # 'min', 'max', or 'mean'
        self.amb_file     = amb_file        # path to ambient sound level file
        self.output_dir   = output_dir      # directory to save plots
        self.file_type    = file_type       # image file type - 'png', 'jpg, 'pdf'
        self.verbose      = verbose         # print of debug information
        #-------------------------------------------------------------------------
        self.block_size   = 65536           # analysis size
        self.cal          = self.calibrate()
        self.amb_analysis = self.analyze(self.amb_file)

        # load sound level requirements from json defition file
        self.slr = json.load(open("sound_level_reqs.json"))
    
    def load(self, audio_file):
        """ Load audio samples from .wav file.
        
        Params
        -------
        audio_file : string
            Path to the audio file to load.   

        Returns
        -------
        x : array
            Audio samples as floating point scaled -1 to 1.
        fs : int
            Sample rate
        """         
        x, fs = sf.read(audio_file)
        self.validate_audio(x, fs)
        if self.verbose:
            print(f"Loaded {x.shape[0]} samples with fs = {fs} from {audio_file}")
        return x, fs

    def one_third_octaves(self, x):
        """ Load audio samples from .wav file.
        
        Params
        -------
        x : array
            Audio samples to analyze with 1/3 octave bands.

        Returns
        -------
        xticks : list
            List of the rounded 1/3 octave bins as strings.
        bands : array
            The ANSI 1/3 octave band numbers.
        energy: array
            Energy measurements for each of the 1/3 octave bands.
        """   
        # window the signal
        w = signal.blackmanharris(x.shape[0])
        x_w = x * w

        # perform frequency domain analysis
        y = fftpack.fft(x_w) #/(x.shape[0])
        y = y[range(x.shape[0]//2)]
        m = np.abs(y)

        # divide into 1/3 octave bands
        # ANSI 1/3 octave bands 10-37
        # (10 Hz - 5000 Hz)
        bands = np.arange(10,38)
        octaves = (2 ** ((bands-30)/3))*(1000)
        xticks = [str(int(round(x_w, 0))) for x_w in octaves][15:]
        
        energy    = []
        step      =  1
        nbins     =  3
        start_bin = 13
        stop_bin  = start_bin + nbins

        for idx, band in enumerate(bands):
            energy.append(np.sum(m[start_bin:stop_bin]))
            start_bin += nbins
            nbins     += step 
            stop_bin  += nbins
            if (idx+1) % 3 == 0:
                step *= 2

        return xticks, bands, np.array(energy)

    def calibrate(self, response_time="fast"):
        """ Determine calibration factor.

        This works by measuring the dBA SPL at the position of the microphone 
        (with a simple sound pressure meter) and then making a recording of this 
        level (preferably while playing something like a 1 kHz sine wave). 
        This function then takes the FFT of this sample and calculates the total
        energy present across frequency. This number is equal to the measured value.
        
        Params
        -------
        response_time : string 
            Desired response time (use the same as the reference meter).

        Returns
        -------
        cal_a : list
            Total engery in the signal in dBA SPL.
        """ 
        # extract the dB SPL target value measured during the calibration
        self.cal_target = int(os.path.basename(self.cal_file).split('_')[1])

        if   response_time == "fast": # 170.67 ms @ 48 kHz
            N = 8192 
        elif response_time == "slow": # 1.365 s  @ 48 kHz
            N = 65536
        else:
            raise ValueError("Invalid response time. Must be 'fast' or 'slow'.")

        # load audio data and get analysis frame
        self.cal_audio, self.fs = self.load(self.cal_file)
        idx = self.find_greatest_energy(self.cal_audio, self.fs, N)
        self.cal_audio = self.cal_audio[idx:idx+N]
        
        # process calibration file (apply A weighting)
        b, a = A_weighting(self.fs)                                 # create filter
        cal_a = signal.lfilter(b, a, self.cal_audio)                # apply filter

        # window the signal
        w = signal.blackmanharris(N)
        cal_aw = cal_a * w

        # perform frequency domain analysis
        y = fftpack.fft(cal_aw) #/(x.shape[0])
        y = y[range(N//2)]

        # sum energy and convert to dBA
        total_energy = (2.0/N) * np.sum(np.power(np.abs(y),2))
        cal_a = 20 * np.log10(total_energy)

        return cal_a 

    def find_greatest_energy(self, data, fs, frame_size):
        """ Find frame of a given length with the greatest RMS energy

        This function searches the supplied audio samples with the
        supplied frame size to find which frame has the greatest energy.
        This frame index is then returned for use in other functions.
        
        Params
        -------
        data : array 
            Audio samples.
        fs : int
            Audio sample rate.
        frame_size : int
            Number of samples in each analysis frame.

        Returns
        -------
        frame_idx : int
            Index of the frame of size frame_size with the greatest RMS energy.
        """ 
        hop_size = int((1/4) * frame_size)
        frames = (data.shape[0] // frame_size) * 4
        rmse = []
        for frame in range(frames):
            x = data[(hop_size*frame):(hop_size*frame)+frame_size]
            frame_rmse = np.sqrt((1/frame_size)*np.sum(np.power(x, 2)))
            rmse.append(frame_rmse)

        return hop_size * np.argmax(rmse)

    def analyze(self, audio_file):
        """ Analyze a given audio sample by 1/3 octave bands
        
        Params
        -------
        audio_file : string 
            Path to the audio file to analyze.

        Returns
        -------
        analysis : dict
            Resulst from the anaylsis.

                audio - Raw audio samples
                bands - ANSI 1/3 octave band numbers
               energy - Calibrated energy in dBA SPL
               xticks - 1/3 Octave bands by frequency (rounded)
            frame_idx - Index of the max. energy frame

        """ 
        # get the audio samples from test file
        x, fs = self.load(audio_file)

        # find the frame with greatest energy
        N = self.block_size
        idx = self.find_greatest_energy(x, fs, N)
        x = x[idx:idx+N]
            
        # apply A weighting filter to account for human perception
        b, a = A_weighting(fs)
        x_a = signal.lfilter(b, a, x)

        # split into 1/3 octave bands
        xticks, bands, energy = self.one_third_octaves(x_a)

        # covnert to dB and apply calibration
        energy = (2.0/N) * np.abs(energy)
        energy = 20 * np.log10(energy)
        energy += self.cal_target - self.cal

        analysis = {
            "audio"     : x,
            "bands"     : bands,
            "energy"    : energy,
            "xticks"    : xticks,
            "frame_idx" : idx}
        
        return analysis

    def run(self, audio_file):
        """ Single run of the analysis of a single test signal.
        
        Params
        -------
        audio_file : string 
            Path to the audio file to analyze.

        """    
        # determine test type based on filename
        test = self.get_test_details(audio_file)

        # get specifications based on test type
        self.band_specs = list(self.slr[test["type"]]["1/3 octave bands"].values())
        self.two_band_spec = self.slr[test["type"]]["two band spec"]

        # run analysis on test file
        analysis = self.analyze(audio_file)

        # create final plots
        plot_title     = f"{test_names[test['type']]} # {test['num']} | {test['date']}"
        plot_filename  = test['file']
        self.generate_plots(plot_title, plot_filename, analysis)

    def generate_plots(self, plot_title, plot_filename, plot_data):
        """ Create plots of the audio time series and frequency response.
        
        Params
        -------
        plot_title : string
            Title of generated plots
        plot_filename : string
            Base filename of the generated plot
        plot_data : dict
            Dictionary of data to be ploted
            
        """
        # storage based upon input filename
        plot_path = os.path.join(self.output_dir, plot_filename)

        # extract plot data
        x          = plot_data['audio']
        bands      = plot_data['bands']
        energy     = plot_data['energy']
        xticks     = plot_data['xticks']
        frame_idx  = plot_data['frame_idx']

        # create title for each plot based on filename?
        ymax = np.max(plot_data['audio'])
        width = 0.25

        # plotting variables
        ts = 1.0/self.fs 			    # sampling period		(seconds)
        n = x.shape[0]					# number of samples 
        t = n/self.fs					# length of signal		(seconds)
        tv = np.linspace(frame_idx*(1/self.fs), 
                         t+frame_idx*(1/self.fs), 
                         num=n)	        # time points vector	(seconds)

        # plot joint time domain and frequency
        fig, ax = plt.subplots(2, 1, figsize=FIGSIZE)
        ax[0].plot(tv, x, color='#1c4b82')
        ax[0].set_xlim(frame_idx*(1/self.fs), (frame_idx+self.block_size)*(1/self.fs))
        ax[0].set_ylim(-ymax,ymax)
        ax[0].set_xlabel('Time (s)')
        ax[0].set_ylabel('Amplitude (dBFS)')
        ax[0].set_title(plot_title)
        ax[0].spines['right'].set_visible(False)
        ax[0].spines['top'].set_visible(False)
        ax[0].grid(which='both', axis='y', linestyle='-')
        ax[0].set_yscale('symlog')

        p1 = ax[1].bar(bands[15:]-width, energy[15:], width, color=COLOR1, zorder=3)
        p2 = ax[1].bar(bands[15:], self.band_specs, width,  color=COLOR2, zorder=3)
        p3 = ax[1].bar(bands[15:]+width, self.amb_analysis['energy'][15:], width,  color=COLOR3, zorder=3)
        ax[1].set_xticks(bands[15:])
        ax[1].set_xticklabels(xticks)
        ax[1].set_xlabel('1/3 Octave Bands - Freq (Hz)')
        ax[1].set_ylabel('Amplitude (dB SPL)')
        p4 = ax[1].axhline(y=self.two_band_spec, color=COLOR4, zorder=4)
        ax[1].spines['right'].set_visible(False)
        ax[1].spines['top'].set_visible(False)
        ax[1].legend((p1[0], p2[0], p3[0], p4), ('Measured', 'Spec', 'Ambient', '2-Band Spec'))
        ax[1].grid(which='major', axis='y', linestyle='-')
        
        plt.savefig(plot_path + '_j' + '.' + self.file_type)
        plt.close()

        # plot frequency alone
        fig, ax = plt.subplots(1, 1, figsize=FIGSIZE)
        p1 = ax.bar(bands[15:]-width, energy[15:], width, color=COLOR1, zorder=3)
        p2 = ax.bar(bands[15:], self.band_specs, width,  color=COLOR2, zorder=3)
        p3 = ax.bar(bands[15:]+width, self.amb_analysis['energy'][15:], width,  color=COLOR3, zorder=3)
        ax.set_xticks(bands[15:])
        ax.set_xticklabels(xticks)
        ax.set_xlabel('1/3 Octave Bands - Freq (Hz)')
        ax.set_ylabel('Amplitude (dB SPL)')
        p4 = ax.axhline(y=self.two_band_spec, color=COLOR4, zorder=4)
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)
        ax.legend((p1[0], p2[0], p3[0], p4), ('Measured', 'Spec', 'Ambient', '2-Band Spec'))
        ax.grid(which='major', axis='y', linestyle='-')
        ax.set_title(plot_title)

        plt.savefig(plot_path + '_f' + '.' + self.file_type)
        plt.close()

    def get_test_details(self, audio_file):
        """ Parse the filename to extract details form the test.
        
        Test recordings MUST conform to the format specifed in the README.
        Please take a look there if you get an error related to parsing.

        Params
        -------
        audio_file : string
            Path to input audio file.

        Returns
        -------
        valid : dict
            Dictionary containing test details.

            type - Testing type 
            date - Date of the test
             num - Test index for particular test type
            file - Filename
            
        """
        try:
            filename = os.path.basename(audio_file).replace(".wav", "")
            details = filename.split("_")
            test = {
                "type" : details[0],
                "date" : details[1],
                "num"  : int(details[2]),
                "file" : filename}
        except Exception as e:
            print(f"Failed to parse {audio_file}!")

        return test

    def validate_audio(self, x, fs):
        """ Validate input audio data.
        
        Ensure input is numpy array of floating point data bewteen -1 and 1, 

        Params
        -------
        x : ndarray
            Input audio data
        fs : int
            Sampling rate of the input audio in Hz

        Returns
        -------
        valid : bool
            True if valid audio
            
        """
        if x.shape[0] < self.block_size:
            raise RuntimeError(f"Invalid length - input file must be {self.block_size} samples long")

        if fs != self.cal_fs:
            raise RuntimeError(f"Invalid sampling rate - input file must have fs = {self.cal_fs}")

        if x.ndim > 1:
            raise RuntimeError(f"Invalid channel count - input file must be mono")

        return True
