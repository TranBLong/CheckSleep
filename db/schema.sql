IF OBJECT_ID(N'dbo.TaiKhoan', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.TaiKhoan (
        MaND INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_TaiKhoan PRIMARY KEY,
        TenDangNhap NVARCHAR(50) NOT NULL
            CONSTRAINT UQ_TaiKhoan_TenDangNhap UNIQUE,
        MatKhau NVARCHAR(255) NOT NULL,
        HoTen NVARCHAR(100) NOT NULL,
        SoDienThoai NVARCHAR(20) NULL,
        VaiTro NVARCHAR(10) NOT NULL
            CONSTRAINT DF_TaiKhoan_VaiTro DEFAULT N'Driver',
        CONSTRAINT CK_TaiKhoan_VaiTro CHECK (VaiTro IN (N'Driver', N'Admin'))
    );
END;
GO

IF COL_LENGTH(N'dbo.TaiKhoan', N'BiKhoa') IS NULL
BEGIN
    ALTER TABLE dbo.TaiKhoan
        ADD BiKhoa BIT NOT NULL
            CONSTRAINT DF_TaiKhoan_BiKhoa DEFAULT 0;
END;
GO

IF OBJECT_ID(N'dbo.CauHinh', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CauHinh (
        MaCauHinh INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_CauHinh PRIMARY KEY,
        MaND INT NOT NULL,
        NguongEAR FLOAT NOT NULL,
        NguongMAR FLOAT NOT NULL,
        NguongPERCLOS FLOAT NOT NULL,
        NguongGatPitch FLOAT NOT NULL,
        SoKhungHinhLienTiep INT NOT NULL,
        ThoiGianHaMuc FLOAT NOT NULL,
        LoaiCanhBao NVARCHAR(20) NOT NULL,
        LuuHinhMinhHoa BIT NOT NULL
            CONSTRAINT DF_CauHinh_LuuHinhMinhHoa DEFAULT 0,
        CONSTRAINT UQ_CauHinh_MaND UNIQUE (MaND),
        CONSTRAINT FK_CauHinh_TaiKhoan FOREIGN KEY (MaND)
            REFERENCES dbo.TaiKhoan(MaND),
        CONSTRAINT CK_CauHinh_Nguong CHECK (
            NguongEAR > 0 AND NguongMAR > 0 AND NguongPERCLOS > 0
            AND NguongGatPitch > 0 AND SoKhungHinhLienTiep > 0
            AND ThoiGianHaMuc >= 0
        )
    );
END;
GO

IF OBJECT_ID(N'dbo.PhienGiamSat', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.PhienGiamSat (
        MaPhien INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_PhienGiamSat PRIMARY KEY,
        MaND INT NOT NULL,
        ThoiGianBatDau DATETIME2 NOT NULL
            CONSTRAINT DF_PhienGiamSat_BatDau DEFAULT SYSUTCDATETIME(),
        ThoiGianKetThuc DATETIME2 NULL,
        TrangThai NVARCHAR(20) NOT NULL,
        SoLanCanhBao INT NOT NULL
            CONSTRAINT DF_PhienGiamSat_SoLanCanhBao DEFAULT 0,
        EAR0 FLOAT NULL,
        MAR0 FLOAT NULL,
        Pitch0 FLOAT NULL,
        CONSTRAINT FK_PhienGiamSat_TaiKhoan FOREIGN KEY (MaND)
            REFERENCES dbo.TaiKhoan(MaND),
        CONSTRAINT CK_PhienGiamSat_SoLanCanhBao CHECK (SoLanCanhBao >= 0)
    );
END;
GO

IF OBJECT_ID(N'dbo.LichSuCanhBao', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.LichSuCanhBao (
        MaCanhBao INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_LichSuCanhBao PRIMARY KEY,
        MaPhien INT NOT NULL,
        ThoiGian DATETIME2 NOT NULL
            CONSTRAINT DF_LichSuCanhBao_ThoiGian DEFAULT SYSUTCDATETIME(),
        DauHieu NVARCHAR(100) NOT NULL,
        GiaTriEAR FLOAT NULL,
        GiaTriMAR FLOAT NULL,
        GiaTriPERCLOS FLOAT NULL,
        GiaTriPitch FLOAT NULL,
        DiemTinCay FLOAT NULL,
        MucCanhBao INT NOT NULL,
        TrangThaiXuLy NVARCHAR(30) NOT NULL
            CONSTRAINT DF_LichSuCanhBao_TrangThaiXuLy DEFAULT N'Chưa xử lý',
        HinhAnhChungMinh NVARCHAR(500) NULL,
        CONSTRAINT FK_LichSuCanhBao_PhienGiamSat FOREIGN KEY (MaPhien)
            REFERENCES dbo.PhienGiamSat(MaPhien),
        CONSTRAINT CK_LichSuCanhBao_MucCanhBao CHECK (MucCanhBao IN (1, 2, 3))
    );
END;
GO
