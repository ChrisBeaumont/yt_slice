from yt.frontends.stream.api import load_uniform_grid
from yt.mods import FixedResolutionBuffer
import numpy as np
import pytest


def _steps(slice):
    return int(np.ceil(1. * (slice.stop - slice.start) / slice.step))


def _fill_slice(slc, dim):
    if not isinstance(slc, slice):
        return slc

    start = slc.start if slc.start is not None else 0
    stop = slc.stop if slc.stop is not None else dim
    step = slc.step if slc.step is not None else 1
    return slice(start, stop, step)


def _sanitize_view(view, dims):
    """
    Convert a view into an explicit tuple of slices and integers

    Parameters
    ----------
    view : argument to __getitem__
    dims : list of dimensions
    """

    if not isinstance(view, tuple):
        view = [view]
    else:
        view = list(view)

    if len(view) < len(dims):
        view = view + [slice(None)] * (len(dims) - len(view))

    for i, v in enumerate(view):
        if isinstance(v, type(Ellipsis)):
            view[i] = slice(None)

    view = [_fill_slice(*viewdim) for viewdim in zip(view, dims)]
    return view


class YtSlice(object):

    """
    Numpy slice interface to Yt Fixed Resolution Buffers.

    YtSlice objects can be indexed using multidimensional slices::

        obj[1::3, 2::4]

    And the appropriate array will be extracted using Yt's Fixed
    Resolution Buffer.
    """

    def __init__(self, pf, field):
        """
        Parameters:
        -----------
        pf : Yt Data Object
           The Yt data to slice into
        field : str
           The name of the Yt field to extract
        """
        self.pf = pf
        self.field = field

    def _slice_args(self, view):
        index, coord = [(i, v) for i, v in enumerate(view)
                        if not isinstance(v, slice)][0]
        coord = 1. * coord / (self.pf.domain_dimensions[index] - 1)
        if coord == 1:
            coord = 1 - 1e-6
        return index, coord

    def _frb_args(self, view):
        sx = sy = None
        dim = self.pf.domain_dimensions

        for i, v in enumerate(view):
            if not isinstance(v, slice):
                continue

            if sx is None:
                sx = view[i]
                nx = dim[i]
            else:
                sy = view[i]
                ny = dim[i]

        l, r = sx.start, sx.stop
        b, t = sy.start, sy.stop
        w = _steps(sx)
        h = _steps(sy)
        bounds = (1. * l / nx, 1. * r / nx, 1. * b / ny, 1. * t / ny)
        return bounds, (h, w)

    def _extract_slice(self, view):
        """
        Extract a slice, using numpy slice syntax

        Parameters
        ----------
        view : tuple of slices or integers

        Returns
        -------
        A numpy array
        """
        sl = self.pf.h.slice(*self._slice_args(view))
        frb = FixedResolutionBuffer(sl, *self._frb_args(view))
        return np.array(frb[self.field]).T

    def _extract_cube(self, view):
        s = map(_steps, view)
        i = min(range(len(view)), key=lambda x: s[x])
        result = np.empty(s)
        for ind in range(s[i]):
            idx = list(view)
            idx2 = [slice(None) for v in view]
            idx2[i] = ind
            idx[i] = view[i].start + ind * view[i].step
            assert idx[i] < view[i].stop
            result[idx2] = self._extract_slice(idx)

        return result

    def __getitem__(self, view):
        view = _sanitize_view(view, self.pf.domain_dimensions)
        assert len(view) == 3

        i = len([v for v in view if isinstance(v, slice)])
        if i == 3:
            return self._extract_cube(view)

        if i == 2:
            return self._extract_slice(view)

        raise NotImplementedError()


class TestSlice(object):

    def setup_method(self, method):
        x = np.arange(64).reshape((4, 4, 4))
        data = dict(data=x)
        y = load_uniform_grid(data, x.shape, 1)
        self.x = x
        self.y = y

    @pytest.mark.parametrize('slc', (np.s_[0, :, :],
                             np.s_[1, :, :],
                             np.s_[2, :, :],
                             np.s_[:, 2, :],
                             np.s_[0, :, 0:1],
                             np.s_[0:1, 0:1, 0],
                             np.s_[1, 0:2, 0:2]))
    def test_nostride(self, slc):
        w = YtSlice(self.y, 'data')
        np.testing.assert_array_almost_equal(w[slc], self.x[slc])

    def test_downsample_axis3(self):
        w = YtSlice(self.y, 'data')
        w = w[0, :, ::2]
        x = (self.x[0, :, ::2] + self.x[0, :, 1::2]) / 2.
        np.testing.assert_array_almost_equal(w, x)

    def test_downsample_axis2(self):
        w = YtSlice(self.y, 'data')
        w = w[0, ::2, :]
        x = (self.x[0, ::2, :] + self.x[0, 1::2, :]) / 2.
        np.testing.assert_array_almost_equal(w, x)

    def test_downsample_axis1(self):
        w = YtSlice(self.y, 'data')
        w = w[::2, :, 0]
        x = (self.x[::2, :, 0] + self.x[1::2, :, 0]) / 2.
        np.testing.assert_array_almost_equal(w, x)

    def test_uneven_downsample(self):
        w = YtSlice(self.y, 'data')
        w = w[0, :, ::3]
        x = (self.x[0, :, 1::2] + self.x[0, :, ::2]) / 2.
        np.testing.assert_array_almost_equal(w, x)

    def test_double_downsample(self):
        w = YtSlice(self.y, 'data')
        w = w[0, ::2, ::2]
        x = (self.x[0, ::2, ::2] + self.x[0, 1::2, 1::2] +
             self.x[0, ::2, 1::2] + self.x[0, 1::2, ::2]) / 4.
        np.testing.assert_array_almost_equal(w, x)


class TestVolume(object):

    def setup_method(self, method):
        x = np.arange(64).reshape((4, 4, 4))
        data = dict(data=x)
        y = load_uniform_grid(data, x.shape, 1)
        self.x = x
        self.y = y

    def test_unsample(self):
        w = YtSlice(self.y, 'data')
        np.testing.assert_array_almost_equal(self.x,
                                             w[:, :, :])

    @pytest.mark.parametrize('slc', (np.s_[:],
                             np.s_[:, :],
                             np.s_[...],
                             np.s_[:, ...],
                             np.s_[:, ..., :],
                             np.s_[..., :]))
    def test_implicit(self, slc):
        w = YtSlice(self.y, 'data')
        np.testing.assert_array_almost_equal(self.x,
                                             w[slc])

    def test_crop(self):
        w = YtSlice(self.y, 'data')
        w = w[0:2, 0:1, 0:1]
        np.testing.assert_array_equal(w, self.x[0:2, 0:1, 0:1])

    @pytest.mark.parametrize('slc', (np.s_[::2, :, :],
                             np.s_[:, ::2, :],
                             np.s_[:, :, ::2],
                             np.s_[:, :, ::3],
                             np.s_[:, :, ::4],
                             np.s_[:, :, ::5]))
    def test_downsample(self, slc):
        w = YtSlice(self.y, 'data')
        w = w[slc]
        np.testing.assert_array_equal(w, self.x[slc])
