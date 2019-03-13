import numpy as np
import soundfile as sf
import scipy.fftpack as fftpack
import matplotlib.pyplot as plt

block_size = 65536 # number of seconds to analyze

# load in data
x, fs = sf.read("audio/wn.wav") # must be fs=48kHz

# take the left channel and block_size samples
if x.ndim > 1:
	x = x[:block_size,0] 	
else:
	x = x[:block_size]

ts = 1.0/fs 			# sampling period		(seconds)
n = x.shape[0]			# number of samples 
t = n/fs				# length of signal		(seconds)

tv = np.linspace(0, t, num=n)	# time points vector	(seconds)
kv = np.arange(n)		# sample points vector 

frq = kv/t
frq = frq[range(n//2)]

print(f"Loaded {x.shape[0]} samples with fs = {fs}\n")

# what size fft should we use? 
# does the specification say over what time period we are intersted?

# perform frequency domain analysis
y = fftpack.fft(x)/(n)
y = y[range(n//2)]
m = abs(y)

# divide into 1/3 octave bands
# ANSI 1/3 octave bands 11-37
# (12.5 Hz - 5000 Hz)
bands = np.arange(10,38)
octaves = (2 ** ((bands-30)/3))*(1000)
xticks = [str(int(x)) for x in octaves]
print(xticks)

power = []
step = 1
nbins = 2
stop = 11 # starting position
for idx, band in enumerate(bands):
	if (idx != 0) and (idx % 3 == 0):
		step *= 2
	nbins += step
	start = stop + 1
	stop  = start + nbins - 1
	with open("f.txt", "a") as f:
		f.write(f"{band} {start} {stop} {frq[start:stop+1]} {nbins}\n")
	power.append(np.sum(m[start:stop]))

# convert power to dB
power = 20 * np.log10(power)

# plot the results
fig, ax = plt.subplots(2, 1, figsize=(20, 10))
ax[0].plot(tv,x)
ax[0].set_xlabel('Time')
ax[0].set_ylabel('Amplitude')
ax[1].plot(bands, power, color='r')
ax[1].set_xticks(bands)
ax[1].set_xticklabels(xticks)

#ax[1].set_xticks(octaves[15:])
#ax[1].set_yscale()
#ax[1].set_xscale('log')
ax[1].set_ylim(-60, 6)
ax[1].set_xlabel('Freq (Hz)')
ax[1].set_ylabel('|Y(freq)|')

plt.show()