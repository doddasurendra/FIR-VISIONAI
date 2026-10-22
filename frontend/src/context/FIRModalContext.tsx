import React, { createContext, useContext, useState } from 'react';
import { FIRFormSelectionModal } from '../components/FIRFormSelectionModal';

interface FIRModalContextType {
  openFIRModal: () => void;
  closeFIRModal: () => void;
  isFIRModalOpen: boolean;
}

const FIRModalContext = createContext<FIRModalContextType | undefined>(undefined);

export const FIRModalProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false);

  const openFIRModal = () => setIsOpen(true);
  const closeFIRModal = () => setIsOpen(false);

  return (
    <FIRModalContext.Provider value={{ openFIRModal, closeFIRModal, isFIRModalOpen: isOpen }}>
      {children}
      {isOpen && <FIRFormSelectionModal onClose={closeFIRModal} />}
    </FIRModalContext.Provider>
  );
};

export const useFIRModal = (): FIRModalContextType => {
  const context = useContext(FIRModalContext);
  if (!context) {
    throw new Error('useFIRModal must be used within a FIRModalProvider');
  }
  return context;
};
